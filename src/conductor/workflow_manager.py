"""
Workflow Manager for Conductor module.

Handles workflow orchestration, message routing, and state transitions
for the medical physics QA workflow.
"""

from typing import Dict, Any, Optional
from src.common.db_utils import DatabaseManager
from src.common.exceptions import ResourceUnavailableError, MQIError
from src.common.logger import get_logger
from src.conductor.state_service import StateService


class WorkflowManager:
    """Manages workflow orchestration and message routing."""
    
    def __init__(self, db_manager: DatabaseManager, config):
        """
        Initialize WorkflowManager.
        
        Args:
            db_manager: Database manager instance
            config: Configuration object
        """
        self.db_manager = db_manager
        self.config = config
        self.state_service = StateService(db_manager)
        self.logger = get_logger(__name__)
        
        # Will be set by main.py when message queue is initialized
        self.publisher = None
        
        # Get workflow configuration
        self.workflow_steps = config.get('workflows.default_qa', [])
        remote_commands_dict = config.get('remote_commands', {})
        self.remote_commands = {
            step: remote_commands_dict.get(step, '')
            for step in self.workflow_steps
        }
    
    def handle_message(self, message_type: str, payload: Dict[str, Any], correlation_id: str):
        """
        Handle incoming messages and route them to appropriate methods.
        
        Args:
            message_type: Type of message received
            payload: Message payload data
            correlation_id: Correlation ID for tracking
        """
        self.logger.info(f"Handling message: {message_type}, correlation_id: {correlation_id}, payload: {payload}")
        
        try:
            if message_type == 'new_case_found':
                self.start_new_workflow(payload['case_id'])
            elif message_type == 'execution_succeeded':
                self.advance_workflow(payload['case_id'])
            elif message_type == 'execution_failed':
                error_info = payload.get('error', 'Unknown error')
                self.handle_workflow_failure(payload['case_id'], error_info)
            elif message_type in ['case_upload_completed', 'download_completed']:
                # These also advance the workflow to next step
                self.advance_workflow(payload['case_id'])
            else:
                self.logger.warning(f"Unknown message type: {message_type}")
        
        except (KeyError, TypeError) as e:
            self.logger.error(f"Invalid message format for {message_type}: {e}", exc_info=True)
            if 'case_id' in payload:
                self.handle_workflow_failure(payload['case_id'], f"Invalid message format: {e}")
        except Exception as e:
            self.logger.error(f"Error handling message {message_type}: {e}", exc_info=True)
            if 'case_id' in payload:
                self.handle_workflow_failure(payload['case_id'], str(e))
    
    def start_new_workflow(self, case_id: str):
        """
        Start a new workflow for a case.
        
        Args:
            case_id: Unique identifier for the case
        """
        self.logger.info(f"Starting workflow for case: {case_id}")
        
        # Check if case already exists (duplicate prevention)
        if not self.state_service.is_new_case(case_id):
            self.logger.warning(f"Case {case_id} already exists, skipping")
            return
        
        # Create new case record
        self.logger.info(f"Creating new case record for {case_id}")
        self.state_service.update_case_status(case_id, 'QUEUED', 'New case detected')
        
        # Start workflow by advancing to first step
        self.advance_workflow(case_id)
    
    def advance_workflow(self, case_id: str):
        """
        Advance workflow to the next step.
        
        Args:
            case_id: Case identifier to advance
        """
        self.logger.info(f"Advancing workflow for case: {case_id}")
        current_status = self.state_service.get_case_current_status(case_id)
        if not current_status:
            self.logger.error(f"Cannot advance workflow: Case {case_id} not found")
            return
        
        self.logger.info(f"Current status for case {case_id} is {current_status}")

        # Determine next step based on current workflow step, not status
        current_workflow_step = self.state_service.get_case_workflow_step(case_id)
        self.logger.info(f"Current workflow step for case {case_id} is {current_workflow_step}")
        next_step = self._get_next_workflow_step(current_workflow_step)
        self.logger.info(f"Next workflow step for case {case_id} is {next_step}")
        
        if next_step is None:
            # Workflow is complete
            self.logger.info(f"Workflow completed for case: {case_id}")
            self.state_service.update_case_status(
                case_id, 'COMPLETED', 'All workflow steps completed successfully', workflow_step=None
            )
            self.state_service.release_gpu_for_case(case_id)
            return
        
        # Try to reserve GPU for the next step
        self.logger.info(f"Attempting to reserve GPU for case {case_id}")
        try:
            gpu_id = self.state_service.reserve_available_gpu(case_id)
            self.logger.info(f"Reserved GPU {gpu_id} for case {case_id}")
            
            # Update case status to PROCESSING and set workflow step
            self.state_service.update_case_status(
                case_id, 'PROCESSING', f'Starting workflow step: {next_step}', workflow_step=next_step
            )
            
            # Generate and publish command
            self._execute_workflow_step(case_id, next_step, gpu_id)
            
        except ResourceUnavailableError as e:
            # No GPUs available, put in waiting state
            self.logger.warning(f"No GPUs available for case {case_id}: {e}")
            self.state_service.update_case_status(
                case_id, 'PENDING_RESOURCE', 'Waiting for available GPU'
            )
    
    def handle_workflow_failure(self, case_id: str, error_info: str):
        """
        Handle workflow failure.
        
        Args:
            case_id: Case that failed
            error_info: Error information
        """
        self.logger.error(f"Workflow failed for case {case_id}: {error_info}")
        
        # Update case status to failed
        self.state_service.update_case_status(
            case_id, 'FAILED', f'Workflow failed: {error_info}'
        )
        
        # Release any reserved GPU
        self.state_service.release_gpu_for_case(case_id)
    
    def _get_next_workflow_step(self, current_workflow_step: Optional[str]) -> Optional[str]:
        """
        Determine the next workflow step based on current workflow step.
        
        Args:
            current_workflow_step: Current workflow step (None if starting)
            
        Returns:
            Next step name, or None if workflow is complete
        """
        # If no current workflow step, start with first step
        if current_workflow_step is None:
            if not self.workflow_steps:
                self.logger.warning("Workflow steps are not defined.")
                return None
            return self.workflow_steps[0]
        
        # Find current step and return next step
        try:
            current_index = self.workflow_steps.index(current_workflow_step)
            if current_index + 1 < len(self.workflow_steps):
                return self.workflow_steps[current_index + 1]
        except ValueError:
            self.logger.error(f"Unknown workflow step: {current_workflow_step}")
        
        return None
    
    def _execute_workflow_step(self, case_id: str, step_name: str, gpu_id: int):
        """
        Execute a workflow step by publishing command message.
        
        Args:
            case_id: Case identifier
            step_name: Name of the step to execute
            gpu_id: Assigned GPU ID
        """
        # Get command template
        command_template = self.remote_commands.get(step_name)
        if not command_template:
            raise MQIError(f"No command template found for step: {step_name}")
        
        # Get configured remote paths
        remote_paths = self.config.get('conductor.remote_paths', {})
        upload_dir = remote_paths.get('upload_dir', '/data')
        download_dir = remote_paths.get('download_dir', '/data')
        
        # Format command with variables
        command = command_template.format(
            case_id=case_id,
            gpu_id=gpu_id,
            rtplan_path=f"{upload_dir}/{case_id}/rtplan.dcm",
            in_dir=f"{upload_dir}/{case_id}/input",
            out_dir=f"{download_dir}/{case_id}/output",
            raw_file=f"{download_dir}/{case_id}/output.raw",
            output_path=f"{download_dir}/{case_id}/processed",
            dicom_file=f"{download_dir}/{case_id}/output.dcm"
        )
        
        # Prepare message payload
        payload = {
            'case_id': case_id,
            'command': command,
            'gpu_id': gpu_id,
            'step': step_name
        }
        
        # Publish execution command
        if self.publisher:
            self.publisher.publish('execute_command', payload, correlation_id=case_id)
            self.logger.info(f"Published execute_command for case {case_id}, step {step_name}")
        else:
            self.logger.error("Publisher not initialized - cannot execute workflow step")