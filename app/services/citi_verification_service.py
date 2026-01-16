from datetime import datetime
import re
from typing import List, Dict, Any, cast
from playwright.async_api import async_playwright, Error as PlaywrightError
from sqlalchemy import select
import instructor

from app.utils.logging import get_logger
from app.config.settings import settings
from app.services.minio_service import MinIOService
from app.services.document_service import get_document_service
from app.db.models import (
    CertificateSubmission,
    Student,
    User,
    VerificationHistory,
    SubmissionStatus,
    VerificationType,
)
from app.schemas.citi_cert_schemas import (
    DocExtractionResult,
    CitiCertificateStructuredOutput,
    Verdict,
    VerificationDecision,
)
from app.services.notifications.utils import create_notification_sync
from app.services.staff.dashboard_stats_service import (
    DashboardStatsService,
    get_dashboard_stats_service,
)
from app.db.session import get_sync_session

logger = get_logger()


class CitiCertVerificationService:
    """
    Service for automating CITI Program certificate verification.
    """

    def __init__(self):
        self.minio_service = MinIOService()
        self.llm_client = instructor.from_provider(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
        )
        self.decision_mapping = {
            VerificationDecision.APPROVE: SubmissionStatus.APPROVED,
            VerificationDecision.REJECT: SubmissionStatus.REJECTED,
            VerificationDecision.MANUAL_REVIEW: SubmissionStatus.MANUAL_REVIEW,
        }
        self.verdict = Verdict(
            decision=VerificationDecision.APPROVE,
            comments=["Submitted certificate is valid and verified by the system."],
        )

    async def verify_certificate_submission(
        self, request_id: str, submission_id: str
    ) -> None:
        """Main method to verify certificate submission end-to-end."""

        logger.info(f"Starting verification for submission ID: {submission_id}")
        submission_data: Dict[str, Any] = {}
        try:
            # Get submission data
            submission_data = await self._get_submission_data(submission_id)
            submission = submission_data["submission"]
            user = submission_data["user"]

            student_name = f"{user.first_name} {user.last_name}"

            # Get submitted file data and extract text
            file_result = await self.minio_service.get_file(submission.file_object_name)
            if not file_result["success"]:
                raise FileNotFoundError(
                    f"Failed to retrieve file {submission.file_object_name}"
                )
            submitted_extraction = await self._extract_document_text(
                submission.filename, file_result["data"]
            )

            # Verification sequence with metadata and extracted text from submitted
            structured_output = await self._verify_with_metadata_and_submitted_text(
                student_name, submitted_extraction
            )
            if not structured_output:
                self.verdict = Verdict(
                    decision=VerificationDecision.REJECT,
                    comments=[
                        "Document metadata or content did not match expected values. Possible tampering detected."
                    ],
                )
                logger.info(f"Verification rejected for submission ID {submission_id}")
                return

            # Download certificate from CITI Program URL for cross-check
            certificate_data = await download_certificate_from_url(
                f"https://{structured_output.verification_url}"
            )
            upload_result = await self.minio_service.upload_bytes(
                data=cast(bytes, certificate_data),
                filename=submission.filename,
                prefix="citi-automated-docs",
                content_type="application/pdf",
            )
            if not upload_result["success"]:
                logger.warning(
                    f"Failed to upload downloaded certificate for cross-check. Continuing verification."
                )
            cross_check_extraction = await self._extract_document_text(
                submission.filename, certificate_data  # type: ignore
            )

            # Cross-check extracted text from downloaded certificate
            miss_matches = await self._verify_with_cross_check_text(
                structured_output, cross_check_extraction
            )
            if miss_matches:
                self.verdict = Verdict(
                    decision=VerificationDecision.REJECT,
                    comments=[
                        f"The following fields did not match during cross-check.\n {', '.join(miss_matches)}"
                    ],
                )
                logger.info(f"Verification rejected for submission ID {submission_id}")
        except Exception as e:
            self.verdict = Verdict(
                decision=VerificationDecision.REJECT,
                comments=[
                    f"Unexpected error occurred during the automated verification process, thus rejected. You can resubmit or contact support."
                ],
            )
            logger.error(
                f"Error during verification for submission ID {submission_id}: {str(e)}"
            )
        finally:
            # Save verification result
            if submission_data["submission"].id:
                await self._save_verification_result(
                    submission_data["submission"], self.verdict
                )
                await self._update_dashboard_stats(
                    submission_data["submission"].requirement_schedule_id,
                    self.verdict.decision,
                )
                await self._notify(
                    request_id,
                    submission_data["student"],
                    submission_data["submission"],
                    self.verdict.decision,
                )
            logger.info(
                f"Verification process completed for submission ID: {submission_id} with decision: {self.verdict.decision.value} and comments: {self.verdict.comments}"
            )

    async def _get_submission_data(self, submission_id: str) -> Dict[str, Any]:
        """Retrieve certificate submission with related data."""
        try:
            with next(get_sync_session()) as db_session:
                row = db_session.execute(
                    select(CertificateSubmission, Student, User)
                    .join(Student, CertificateSubmission.student_id == Student.id)
                    .join(User, Student.user_id == User.id)
                    .where(CertificateSubmission.id == submission_id)
                ).first()

                if not row:
                    raise ValueError(
                        f"Certificate submission with ID {submission_id} not found."
                    )

                return dict(submission=row[0], student=row[1], user=row[2])
        except Exception as e:
            raise e

    async def _extract_document_text(
        self, filename: str, file_content: bytes
    ) -> DocExtractionResult:
        """Extract text from document stored in MinIO."""
        try:
            document_service = get_document_service()
            extraction_result = await document_service.extract_text(
                file_content, filename
            )
            return extraction_result
        except Exception as e:
            raise e

    async def _verify_with_metadata_and_submitted_text(
        self,
        student_name: str,
        extraction_result: DocExtractionResult,
    ) -> CitiCertificateStructuredOutput | None:
        try:
            doc_metadata = extraction_result.metadata

            structured_output = cast(
                CitiCertificateStructuredOutput,
                self.llm_client.chat.completions.create(
                    response_model=CitiCertificateStructuredOutput,
                    messages=[
                        {
                            "role": "user",
                            "content": f"Extract data from the following text:\n{extraction_result.text}",
                        }
                    ],
                ),
            )

            if not doc_metadata:
                return None

            try:
                creation_date = await self._format_pdf_date(
                    doc_metadata.creation_date or ""
                )
                if creation_date != structured_output.generated_on:
                    return None
            except ValueError as e:
                raise e

            if (
                student_name.replace(" ", "").lower()
                != structured_output.student_name.replace(" ", "").lower()
            ):
                return None

            valid_url_pattern = re.compile(
                r"^(?:https:\\)?www\.citiprogram\.org/verify/\?w(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})-(\d{8})$",
                re.IGNORECASE,
            )

            groups = valid_url_pattern.search(structured_output.verification_url)
            if not groups or groups.group(1) != structured_output.record_id:
                return None

            return structured_output
        except Exception as e:
            logger.error(str(e))
            raise e

    async def _verify_with_cross_check_text(
        self,
        structured_output: CitiCertificateStructuredOutput,
        cross_check_extraction: DocExtractionResult,
    ) -> List[str]:
        try:
            cross_check_output = cast(
                CitiCertificateStructuredOutput,
                self.llm_client.chat.completions.create(
                    response_model=CitiCertificateStructuredOutput,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a precise data extraction assistant specializing in academic certificates. "
                                "Your task is to extract information from CITI Program Completion Reports.\n\n"
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Extract the certificate details from the following raw text:\n\n### RAW TEXT ###\n{cross_check_extraction.text}\n### END RAW TEXT ###",
                        },
                    ],
                    temperature=0,  # to ensure consistency
                ),
            )

            def clean(val):
                # LLM extraction is not effecient with values written in parentheses
                # e.g., curriculum_group might be either "Responsible Conduct of Research (Curriculum Group)" or "Responsible Conduct of Research"
                # similarly, for course_learner_group, it is either "Undergraduate Students (RCR)" or "Undergraduate Students"
                # thus we need to clean those up

                return (
                    re.sub(r"\(.*?\)", "", str(val)).replace(" ", "").lower()
                    if val
                    else ""
                )

            fields = [
                f for f in structured_output.model_dump().keys() if f != "generated_on"
            ]

            return [
                " ".join(field.split("_")).title()
                for field in fields
                if clean(getattr(structured_output, field))
                != clean(getattr(cross_check_output, field))
            ]
        except Exception as e:
            raise e

    async def _format_pdf_date(self, date_str: str) -> str:
        # Convert D:20250114031902-05'00' to 14-Jan-2025
        dt = datetime.strptime(date_str.replace("D:", "")[:8], "%Y%m%d")
        return dt.strftime("%d-%b-%Y")

    async def _save_verification_result(
        self, submission: CertificateSubmission, verdict: Verdict
    ) -> None:
        """Save verification results to the database."""
        try:
            with next(get_sync_session()) as db_session:
                old_status = submission.submission_status
                new_status = self.decision_mapping[verdict.decision]

                # Update submission record
                submission = db_session.get_one(CertificateSubmission, submission.id)
                submission.submission_status = new_status

                # Create verification history
                verification_history = VerificationHistory(
                    submission_id=submission.id,
                    verifier_id=None,
                    verification_type=VerificationType.AGENT,
                    old_status=old_status,
                    new_status=new_status,
                    comments="\n".join(verdict.comments),
                )

                db_session.add(verification_history)
                db_session.commit()
        except Exception as e:
            raise e

    async def _update_dashboard_stats(
        self, schedule_id: str, decision: VerificationDecision
    ) -> None:
        """Update dashboard statistics based on the validation decision."""
        with next(get_sync_session()) as db_session:
            dashboard_stats_service: DashboardStatsService = (
                get_dashboard_stats_service(db_session)
            )

            decision_deltas = {
                VerificationDecision.APPROVE: {
                    "approved_count_delta": 1,
                    "pending_count_delta": -1,
                    "agent_verification_count_delta": 1,
                },
                VerificationDecision.REJECT: {
                    "rejected_count_delta": 1,
                    "pending_count_delta": -1,
                },
                VerificationDecision.MANUAL_REVIEW: {
                    "manual_review_count_delta": 1,
                    "pending_count_delta": -1,
                },
            }

            deltas = decision_deltas[decision]
            if deltas:
                await dashboard_stats_service.update_dashboard_stats_by_schedule(
                    requirement_schedule_id=schedule_id, **deltas
                )

    async def _notify(
        self,
        request_id: str,
        student: Student,
        submission: CertificateSubmission,
        decision: VerificationDecision,
    ) -> None:
        """Placeholder for notification logic."""
        notification_codes = {
            VerificationDecision.APPROVE: "certificate_submission_verify",
            VerificationDecision.REJECT: "certificate_submission_reject",
            VerificationDecision.MANUAL_REVIEW: "certificate_submission_request",
        }
        create_notification_sync(
            request_id=request_id,
            notification_code=notification_codes[decision],
            entity_id=submission.id,
            actor_type="system",
            recipient_ids=[student.user_id],
            actor_id=None,
            scheduled_for=None,
            expires_at=None,
            in_app_enabled=True,
            line_app_enabled=True,
        )


def get_citi_verification_service() -> CitiCertVerificationService:
    """Get CITI Cert Verification Service instance."""
    return CitiCertVerificationService()


async def download_certificate_from_url(url: str) -> bytes:
    """Download certificate from CITI Program URL using Playwright automation."""
    if not all([settings.CITI_USERNAME, settings.CITI_PASSWORD]):
        raise Exception("CITI credentials not configured")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=settings.CITI_HEADLESS,
                timeout=settings.CITI_TIMEOUT,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )

            context = await browser.new_context(
                accept_downloads=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )

            certificate_data: bytes = b""

            try:
                # Navigate and login
                page = await context.new_page()
                await page.goto(url, timeout=settings.CITI_TIMEOUT)
                await page.wait_for_load_state("networkidle")

                # Handle login
                async with page.context.expect_page() as new_page_info:
                    await page.get_by_role(
                        "link",
                        name=re.compile("log in for easier access.", re.IGNORECASE),
                    ).click()

                login_page = await new_page_info.value
                await login_page.wait_for_load_state("networkidle")
                await login_page.fill("#main-login-username", settings.CITI_USERNAME)
                await login_page.fill("#main-login-password", settings.CITI_PASSWORD)
                await login_page.click('input[type="submit"][value="Log In"]')

                # Capture PDF
                pdf_page = await context.new_page()

                async def handle_pdf_requests(route):
                    nonlocal certificate_data
                    response = await route.fetch()
                    certificate_data = await response.body()
                    logger.info(f"PDF captured ({len(certificate_data)} bytes)")
                    await route.abort()

                await pdf_page.route(
                    "https://www.citiprogram.org/verify/?*", handle_pdf_requests
                )

                """
                        Navigating to a URL which triggers the download from the start, using page.got(), will throw a Playwright navigation error. This is an expected behavior in headless mode. The page.goto() function is to navigate to a URL and wait for the resource to load (like loading the content in a new tab). Normally, in a headed browser, this would work fine as the Chromium borwser open a new tab and embed the captured PDF into the embedded PDF viewer. However, in headless Chromium or Firefox (both headed and headless), the navigation will not happend as the PDF content is directly downloaded. This throws the following error:
                            if (browserName === 'chromium') {
                                expect(responseOrError instanceof Error).toBeTruthy();
                                expect(responseOrError.message).toContain('net::ERR_ABORTED');
                                expect(page.url()).toBe('about:blank');
                            } else if (browserName === 'webkit') {
                                expect(responseOrError instanceof Error).toBeTruthy();
                                expect(responseOrError.message).toContain('Download is starting');
                                expect(page.url()).toBe('about:blank');
                            } else {
                                expect(responseOrError instanceof Error).toBeTruthy();
                                expect(responseOrError.message).toContain('Download is starting');
                            }
                        
                        Playwright Docs:
                        https://playwright.dev/python/docs/network#glob-url-patterns

                        Issue References:
                        https://github.com/microsoft/playwright/issues/18430
                        https://issues.chromium.org/issues/41342415
                        https://github.com/microsoft/playwright/issues/7822
                        https://github.com/microsoft/playwright/issues/3509#issuecomment-675441299
                    """
                try:
                    await pdf_page.goto(url, timeout=settings.CITI_TIMEOUT)
                except PlaywrightError:
                    logger.warning(
                        "Request aborted - this may be expected behavior in headless mode"
                    )

            except PlaywrightError as e:
                raise e
            finally:
                await context.close()
                await browser.close()

            return certificate_data

    except Exception as e:
        raise e
