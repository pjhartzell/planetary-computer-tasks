import logging
from time import perf_counter
from typing import Any, Optional, Tuple

from azure.identity import DefaultAzureCredential
from azure.storage.queue import (
    BinaryBase64DecodePolicy,
    BinaryBase64EncodePolicy,
    QueueClient,
    QueueServiceClient,
)

from pctasks.core.models.event import NotificationSubmitMessage
from pctasks.core.models.operation import OperationSubmitMessage
from pctasks.core.models.task import TaskConfig
from pctasks.core.models.workflow import WorkflowSubmitMessage
from pctasks.submit.settings import SubmitSettings

logger = logging.getLogger(__name__)


def _get_queue_client(
    settings: SubmitSettings,
) -> Tuple[QueueServiceClient, QueueClient]:
    service_client: QueueServiceClient

    queue_name = settings.queue_name
    if settings.connection_string:
        service_client = QueueServiceClient.from_connection_string(
            settings.connection_string
        )
    else:
        account_url = settings.get_submit_queue_url()
        credential: Optional[str] = settings.account_key or settings.sas_token
        service_client = QueueServiceClient(
            account_url,
            credential=credential or DefaultAzureCredential(),
        )

    return (
        service_client,
        service_client.get_queue_client(
            queue_name,
            message_encode_policy=BinaryBase64EncodePolicy(),
            message_decode_policy=BinaryBase64DecodePolicy(),
        ),
    )


class SubmitClient:
    def __init__(self, settings: SubmitSettings) -> None:
        self.settings = settings
        self.queue_client = None
        self.service_client = None

    def __enter__(self) -> "SubmitClient":
        self.service_client, self.queue_client = _get_queue_client(self.settings)

        return self

    def __exit__(self, *args: Any) -> None:
        if self.queue_client:
            self.queue_client.close()
            self.queue_client = None
        if self.service_client:
            self.service_client.close()
            self.service_client = None

    def _transform_task_config(self, task_config: TaskConfig) -> None:
        # Repace image keys with configured images.
        if task_config.image_key:
            image_config = self.settings.image_keys.get(task_config.image_key)
            if image_config:
                logger.debug(
                    f"Setting image to '{image_config.image}' from settings..."
                )
                task_config.image = image_config.image
                task_config.image_key = None
                task_config.environment = image_config.merge_env(
                    task_config.environment
                )

    def submit_workflow(self, message: WorkflowSubmitMessage) -> str:
        """Submits a workflow for processing.

        Returns the run ID associated with this submission, which
        was either set on the message or from the Queue submission.
        """
        if not self.queue_client:
            raise RuntimeError("SubmitClient is not opened. Use as a context manager.")

        for job in message.workflow.jobs.values():
            for task in job.tasks:
                self._transform_task_config(task)

        logger.debug("Submitting workflow...")
        start = perf_counter()
        _ = self.queue_client.send_message(message.json(exclude_none=True).encode())
        end = perf_counter()
        logger.debug(f"Submit took {end - start:.2f} seconds.")
        return message.run_id

    def submit_notification(self, message: NotificationSubmitMessage) -> str:
        """Submits a NotificationMessage for processing.

        Returns the run ID associated with this submission, which
        was either set on the message or from the Queue submission.
        """
        if not self.queue_client:
            raise RuntimeError("SubmitClient is not opened. Use as a context manager.")

        logger.debug("Submitting notification...")
        start = perf_counter()
        _ = self.queue_client.send_message(message.json(exclude_none=True).encode())
        end = perf_counter()
        logger.debug(f"Submit took {end - start:.2f} seconds.")
        return str(message.processing_id.run_id)

    def submit_operation(self, message: OperationSubmitMessage) -> str:
        ...
