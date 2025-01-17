import logging
from typing import Any, Dict

import azure.functions as func

from pctasks.core.cosmos.containers.records import RecordsContainer
from pctasks.core.models.workflow import WorkflowRecord, WorkflowRecordType

logger = logging.getLogger(__name__)


async def main(container: func.DocumentList) -> None:
    for document in container:
        data: Dict[str, Any] = document.data
        _type = data.get("type")

        if _type == WorkflowRecordType.WORKFLOW:
            handle_workflow(data)
        else:
            pass


def handle_workflow(data: Dict[str, Any]) -> None:
    """Handle a workflow record."""
    record = WorkflowRecord.parse_obj(data)

    container = RecordsContainer(WorkflowRecord)
    container.put(record)
    logger.info(f"Workflow {record.workflow_id} saved to single partition container.")
