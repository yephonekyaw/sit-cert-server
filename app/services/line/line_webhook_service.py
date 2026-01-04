import re
from typing import Optional, cast
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from uuid import uuid4

from linebot.v3.webhook import WebhookHandler
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    FollowEvent,
    Event,
    UserSource,
)
from linebot.v3.messaging import (
    Configuration,
    AsyncApiClient,
    AsyncMessagingApi,
    ReplyMessageRequest,
    TextMessage,
    PushMessageRequest,
)

from app.db.models import Student
from app.config.settings import settings
from app.utils.logging import get_logger
from app.services.line.line_token_management_service import (
    get_line_channel_token_service,
)

logger = get_logger()


class LineWebhookService:
    """Service for handling LINE webhook events and sending notifications"""

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.handler = WebhookHandler(settings.LINE_CHANNEL_SECRET)

        # Register event handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register webhook event handlers"""
        self.handler.add(FollowEvent)(self._handle_follow_event)
        self.handler.add(MessageEvent, message=TextMessageContent)(
            self._handle_message_event
        )
        self.handler.default()(self._handle_default_event)

    async def handle_webhook_events(self, body: str, signature: str) -> None:
        """Handle incoming webhook events"""
        try:
            self.handler.handle(body, signature)
        except Exception as e:
            logger.error(f"Error handling webhook events: {str(e)}")
            raise

    async def _get_configuration(self) -> Optional[Configuration]:
        """Get LINE messaging API configuration"""
        try:
            line_channel_token_service = get_line_channel_token_service(self.db_session)
            line_access_token = (
                await line_channel_token_service.get_messaging_access_token()
            )

            if line_access_token:
                return Configuration(access_token=line_access_token)
            else:
                line_access_token_row = (
                    await line_channel_token_service.generate_and_store_new_token()
                )
                if line_access_token_row:
                    return Configuration(
                        access_token=line_access_token_row.access_token
                    )
                return None
        except Exception as e:
            logger.error(f"Failed to get LINE configuration: {str(e)}")
            return None

    def _handle_follow_event(self, event: FollowEvent, *args) -> None:
        """Handle follow events - user follows the LINE bot"""
        user_id = cast(UserSource, event.source).user_id

        # Check if user_id already exists in database
        student = self._find_student_by_line_id(str(user_id))

        if student:
            # User already registered, do nothing for now
            return

        # User not found, ask for student ID
        welcome_message = (
            "Welcome to SIT Cert LINE Bot!\n"
            "To get started and receive notifications about your certificate requirements, "
            "please send us your 11-digit Student ID.\n"
            "Example: 66130500830\n"
            "We'll link your LINE account to your student profile so you can receive "
            "important updates about submission deadlines and requirements."
        )

        self._reply_message(event.reply_token, welcome_message)

    def _handle_message_event(self, event: MessageEvent, *args) -> None:
        """Handle message events - user sends text message"""
        if not isinstance(event.message, TextMessageContent):
            return

        user_id = cast(UserSource, event.source).user_id
        message_text = event.message.text.strip()

        # Try to extract 11-digit student ID from message
        student_id_match = re.search(r"\b(\d{11})\b", message_text)

        if student_id_match:
            student_id = student_id_match.group(1)
            self._process_student_id_registration(
                str(event.reply_token), str(user_id), student_id
            )
        else:
            # No student ID found, check if user is already registered
            student = self._find_student_by_line_id(str(user_id))

            if student:
                # User is registered, provide help
                user_name = f"{student.user.first_name} {student.user.last_name}"
                help_message = (
                    f"Hello {user_name}!\n"
                    "How can I help you today?\n"
                    "I can assist you with:\n"
                    "• Certificate submission reminders\n"
                    "• Deadline notifications\n"
                    "• Requirement status updates\n"
                    "You'll automatically receive notifications when you have upcoming deadlines or important updates."
                )
                self._reply_message(str(event.reply_token), help_message)
            else:
                # User not registered, ask for student ID
                registration_message = (
                    "To use this service, please provide your 11-digit Student ID.\n"
                    "Example: 66130500830\n"
                    "This will link your LINE account to your student profile for notifications."
                )
                self._reply_message(str(event.reply_token), registration_message)

    def _handle_default_event(self, event: Event, *args) -> None:
        """Handle unsupported events"""
        # Try to reply if the event has a reply token
        if hasattr(event, "reply_token") and getattr(event, "reply_token", None):
            message = (
                "Sorry, I'm unable to process this type of message or event.\n"
                "I can help you with:\n"
                "• Registering your Student ID\n"
                "• Receiving certificate requirement notifications\n"
                "Please send your 11-digit Student ID to get started!"
            )
            self._reply_message(getattr(event, "reply_token"), message)

    def _process_student_id_registration(
        self, reply_token: str, line_user_id: str, student_id: str
    ) -> None:
        """Process student ID registration"""
        try:
            # Find student by student ID
            result = self.db_session.execute(
                select(Student)
                .options(selectinload(Student.user))
                .where(Student.student_id == student_id)
            )
            student = result.scalar_one_or_none()

            if not student:
                error_message = (
                    f"Student ID '{student_id}' not found in our system.\n"
                    "Please check your Student ID and try again, or contact the academic office if you believe this is an error."
                )
                self._reply_message(reply_token, error_message)
                return

            # Check if this LINE user is already registered to another student
            existing_student = self._find_student_by_line_id(line_user_id)
            if existing_student and existing_student.id != student.id:
                error_message = (
                    "This LINE account is already linked to another student profile.\n"
                    "Each LINE account can only be linked to one student ID. "
                    "Please contact the academic office if you need assistance."
                )
                self._reply_message(reply_token, error_message)
                return

            # Update student's LINE application ID
            student.line_application_id = line_user_id
            self.db_session.commit()

            success_message = (
                f"Your LINE account has been successfully linked!\n"
                f"Welcome, {student.user.first_name} {student.user.last_name}!\n"
                "You will now receive notifications about:\n"
                "• Upcoming certificate submission deadlines\n"
                "• Requirement reminders\n"
                "• Important updates from the academic office\n"
                "Thank you for using SIT Cert LINE Bot!"
            )
            self._reply_message(reply_token, success_message)

        except Exception as e:
            logger.error(f"Error processing student registration: {str(e)}")
            error_message = (
                "An error occurred while processing your registration.\n"
                "Please try again later or contact the academic office for assistance."
            )
            self._reply_message(reply_token, error_message)

    def _find_student_by_line_id(self, line_user_id: str) -> Optional[Student]:
        """Find student by LINE application ID"""
        try:
            result = self.db_session.execute(
                select(Student)
                .options(selectinload(Student.user))
                .where(Student.line_application_id == line_user_id)
            )
            return result.scalar_one_or_none()
        except Exception:
            return None

    def _reply_message(self, reply_token: str, message: str) -> None:
        """Reply to a LINE message"""
        import asyncio

        async def _send_reply():
            configuration = await self._get_configuration()
            if not configuration:
                return

            try:
                async with AsyncApiClient(configuration=configuration) as api_client:
                    line_bot_api = AsyncMessagingApi(api_client)
                    await line_bot_api.reply_message(
                        ReplyMessageRequest(
                            replyToken=reply_token,
                            messages=[
                                TextMessage(
                                    text=message, quickReply=None, quoteToken=None
                                )
                            ],
                            notificationDisabled=False,
                        )
                    )
            except Exception as e:
                logger.error(f"Failed to send reply message: {str(e)}")

        # Run async function in background
        asyncio.create_task(_send_reply())

    async def send_push_notification(
        self, line_user_id: str, subject: str, body: str
    ) -> bool:
        """Send push notification to a specific LINE user"""
        configuration = await self._get_configuration()
        if not configuration:
            return False

        try:
            message_text = f"{subject}\n{body}" if subject else body

            async with AsyncApiClient(configuration=configuration) as api_client:
                line_bot_api = AsyncMessagingApi(api_client)
                await line_bot_api.push_message(
                    PushMessageRequest(
                        to=line_user_id,
                        messages=[
                            TextMessage(
                                text=message_text, quickReply=None, quoteToken=None
                            )
                        ],
                        notificationDisabled=False,
                        customAggregationUnits=None,
                    ),
                    x_line_retry_key=str(uuid4()),
                )
                return True

        except Exception as e:
            logger.error(f"Failed to send push notification: {str(e)}")
            return False

    def validate_line_user_exists(self, line_user_id: str) -> bool:
        """Validate that a LINE user ID exists in our database"""
        student = self._find_student_by_line_id(line_user_id)
        return student is not None

    def get_student_by_line_id(self, line_user_id: str) -> Optional[Student]:
        """Get student information by LINE user ID"""
        return self._find_student_by_line_id(line_user_id)


def get_line_webhook_service(db_session: Session) -> LineWebhookService:
    """Dependency function to create LineWebhookService instance"""
    return LineWebhookService(db_session)
