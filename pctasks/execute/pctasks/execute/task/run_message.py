import logging
import os
from datetime import datetime, timedelta
from typing import Union
from uuid import uuid1

from azure.core.credentials import AzureNamedKeyCredential
from azure.data.tables import TableSasPermissions, generate_table_sas
from azure.storage.blob import BlobSasPermissions, generate_blob_sas
from azure.storage.queue import QueueSasPermissions, generate_queue_sas

from pctasks.core.constants import ENV_VAR_TASK_APPINSIGHTS_KEY
from pctasks.core.models.config import (
    BlobConfig,
    ImageConfig,
    QueueConnStrConfig,
    QueueSasConfig,
    TableSasConfig,
)
from pctasks.core.models.task import TaskRunConfig, TaskRunMessage
from pctasks.core.models.tokens import StorageAccountTokens
from pctasks.execute.models import TaskSubmitMessage
from pctasks.execute.secrets.base import SecretsProvider
from pctasks.execute.secrets.keyvault import KeyvaultSecretsProvider
from pctasks.execute.secrets.local import LocalSecretsProvider
from pctasks.execute.settings import ExecutorSettings
from pctasks.execute.utils import get_run_log_path, get_task_output_path

logger = logging.getLogger(__name__)


def submit_msg_to_task_run_msg(
    submit_msg: TaskSubmitMessage,
    run_id: str,
    settings: ExecutorSettings,
) -> TaskRunMessage:
    """
    Convert a submit message to an exec message.
    """
    if not submit_msg.instance_id:
        raise ValueError("submit_msg.instance_id is required")

    target_environment = submit_msg.target_environment
    job_id = submit_msg.job_id
    task_config = submit_msg.config
    task_id = task_config.id

    event_logger_app_insights_key = os.environ.get(ENV_VAR_TASK_APPINSIGHTS_KEY)

    environment = submit_msg.config.environment

    # --Handle image key--

    if not task_config.image:
        image_key = task_config.image_key
        if not image_key:
            # Should have been handled by model validation
            raise ValueError("Must specify either image_key or image.")

        logger.info(f"No image specified, using image key '{image_key}'")

        with settings.get_image_key_table() as image_key_table:
            image_config = image_key_table.get_image(image_key, target_environment)

        if image_config is None:
            raise ValueError(
                f"Image for image key '{image_key}' and target environment "
                f"'{target_environment}' not found "
                f"in table {settings.image_key_table_name}."
            )

        # Merge the environment variables from the image-key table into
        # this environment. Explicit environment takes precedence.
        if environment:
            if image_config.environment:
                logger.info(
                    "Merging environment from image key table "
                    "into submit msg environment."
                )
                environment = {
                    **(image_config.get_environment() or {}),
                    **environment,
                }
        else:
            logger.info("Setting image key environment as task environment.")
            environment = image_config.get_environment()
    else:
        image_config = ImageConfig(image=task_config.image)

    # --Handle secrets--

    secrets_provider: SecretsProvider
    if settings.local_secrets:
        secrets_provider = LocalSecretsProvider()
    else:
        assert settings.keyvault_url  # Handled by model validation
        secrets_provider = KeyvaultSecretsProvider.get_provider(settings.keyvault_url)

    with secrets_provider:
        if environment:
            environment = secrets_provider.substitute_secrets(environment)

        tokens = submit_msg.tokens
        if tokens:
            tokens = {
                account: StorageAccountTokens(
                    **secrets_provider.substitute_secrets(v.dict())
                )
                for account, v in tokens.items()
            }

    # --Handle configuration--

    # Queues

    signal_queue_config: Union[QueueConnStrConfig, QueueSasConfig]

    if settings.dev:
        assert isinstance(settings.signal_queue, QueueConnStrConfig)
        signal_queue_config = settings.signal_queue.to_queue_config()
    else:
        signal_sas_token = generate_queue_sas(
            account_name=settings.signal_queue_account_name,
            account_key=settings.signal_queue_account_key,
            queue_name=settings.signal_queue.queue_name,
            start=datetime.now(),
            expiry=datetime.utcnow() + timedelta(hours=24 * 7),
            permission=QueueSasPermissions(add=True),
        )

        signal_queue_config = QueueSasConfig(
            account_url=(
                f"https://{settings.signal_queue_account_name}.queue.core.windows.net"
            ),
            queue_name=settings.signal_queue.queue_name,
            sas_token=signal_sas_token,
        )

    # Tables

    tables_cred = AzureNamedKeyCredential(
        name=settings.tables_account_name, key=settings.tables_account_key
    )

    task_runs_table_sas_token = generate_table_sas(
        credential=tables_cred,
        table_name=settings.task_run_record_table_name,
        start=datetime.now(),
        expiry=datetime.utcnow() + timedelta(hours=24 * 7),
        permission=TableSasPermissions(read=True, write=True, update=True),
    )

    task_runs_table_config = TableSasConfig(
        account_url=settings.tables_account_url,
        table_name=settings.task_run_record_table_name,
        sas_token=task_runs_table_sas_token,
    )

    # Blob
    log_path = get_run_log_path(job_id, task_id, run_id)
    log_uri = (
        f"blob://{settings.blob_account_name}/{settings.log_blob_container}/{log_path}"
    )
    log_blob_sas_token = generate_blob_sas(
        account_name=settings.blob_account_name,
        account_key=settings.blob_account_key,
        container_name=settings.log_blob_container,
        blob_name=log_path,
        start=datetime.now(),
        expiry=datetime.utcnow() + timedelta(hours=24 * 7),
        permission=BlobSasPermissions(write=True),
    )
    log_blob_config = BlobConfig(
        uri=log_uri, sas_token=log_blob_sas_token, account_url=settings.blob_account_url
    )

    output_path = get_task_output_path(job_id, task_id, run_id)
    output_uri = (
        f"blob://{settings.blob_account_name}/"
        f"{settings.log_blob_container}/{output_path}"
    )
    output_blob_sas_token = generate_blob_sas(
        account_name=settings.blob_account_name,
        account_key=settings.blob_account_key,
        container_name=settings.log_blob_container,
        blob_name=output_path,
        start=datetime.now(),
        expiry=datetime.utcnow() + timedelta(hours=24 * 7),
        permission=BlobSasPermissions(write=True),
    )
    output_blob_config = BlobConfig(
        uri=output_uri,
        sas_token=output_blob_sas_token,
        account_url=settings.blob_account_url,
    )

    config = TaskRunConfig(
        image=image_config.image,
        run_id=submit_msg.run_id,
        job_id=submit_msg.job_id,
        task_id=submit_msg.config.id,
        signal_key=uuid1().hex,
        signal_target_id=submit_msg.instance_id,
        task=task_config.task,
        environment=environment,
        tokens=tokens,
        signal_queue=signal_queue_config,
        task_runs_table_config=task_runs_table_config,
        output_blob_config=output_blob_config,
        log_blob_config=log_blob_config,
        event_logger_app_insights_key=event_logger_app_insights_key,
    )

    return TaskRunMessage(args=task_config.args, config=config)
