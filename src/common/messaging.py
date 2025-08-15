"""
RabbitMQ messaging wrapper for MQI Communicator system.
"""

import json
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Callable, Optional, TYPE_CHECKING
from .exceptions import NetworkError
from .logger import get_logger

if TYPE_CHECKING:
    import pika
else:
    try:
        import pika
    except ImportError:
        pika = None  # type: ignore


class MessagingError(Exception):
    """Base exception for messaging operations."""
    pass


class MessageQueue:
    """RabbitMQ wrapper for message publishing and consuming."""
    
    def __init__(self, connection_params: Dict[str, Any], config: Optional[Dict[str, Any]] = None, db_manager=None):
        """
        Initialize message queue connection.
        
        Args:
            connection_params: RabbitMQ connection parameters
            config: Configuration dict containing messaging settings
            db_manager: Database manager instance for logging (optional)
        """
        self.connection_params = connection_params
        self.connection: Optional[Any] = None  # pika.BlockingConnection when available
        self.channel: Optional[Any] = None  # pika.channel.Channel when available
        self.logger = get_logger(__name__, db_manager)
        self.config = config or {}
        self.max_retries = self.config.get('messaging', {}).get('max_retries', 3)
    
    def connect(self, max_retries: int = 3, base_delay: float = 1.0) -> None:
        """
        Establish connection to RabbitMQ with retry mechanism.
        
        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay for exponential backoff (seconds)
        """
        if pika is None:
            raise NetworkError("pika library is not installed. Install it with 'pip install pika'")
        
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                connection = pika.BlockingConnection(pika.URLParameters(**self.connection_params))
                self.connection = connection
                self.channel = connection.channel()
                self.logger.info(f"Successfully connected to message queue: {self.connection_params.get('url', 'unknown')}")
                return  # Success
                
            except Exception as e:
                last_exception = e
                
                if attempt < max_retries:
                    # Calculate exponential backoff delay
                    delay = base_delay * (2 ** attempt)
                    self.logger.warning(f"Message queue connection attempt {attempt + 1}/{max_retries + 1} failed for {self.connection_params.get('url', 'unknown')}: {e}. Retrying in {delay:.1f}s")
                    time.sleep(delay)
                else:
                    # Final attempt failed
                    self.logger.error(f"Final connection attempt {attempt + 1}/{max_retries + 1} failed for {self.connection_params.get('url', 'unknown')}: {e}")
                    break
        
        # All attempts failed
        raise NetworkError(f"Failed to connect to message queue after {max_retries + 1} attempts: {last_exception}")
    
    def _setup_dlx_and_dlq(self, queue_name: str) -> None:
        """
        Setup Dead Letter Exchange (DLX) and Dead Letter Queue (DLQ) for a queue.
        
        Args:
            queue_name: Name of the primary queue
        """
        if self.channel is None:
            raise NetworkError("Channel not connected. Call connect() first.")
        
        dlx_exchange = 'dlx_exchange'
        dlq_name = f'{queue_name}.dlq'
        
        # Declare Dead Letter Exchange
        self.channel.exchange_declare(exchange=dlx_exchange, exchange_type='direct', durable=True)
        
        # Declare Dead Letter Queue
        self.channel.queue_declare(queue=dlq_name, durable=True)
        
        # Bind DLQ to DLX
        self.channel.queue_bind(queue=dlq_name, exchange=dlx_exchange, routing_key=dlq_name)
        
        self.logger.debug(f"Setup DLX and DLQ for queue '{queue_name}': DLX='{dlx_exchange}', DLQ='{dlq_name}'")
    
    def publish_message(self, queue_name: str, command: str, payload: Dict[str, Any], 
                       correlation_id: Optional[str] = None, retry_count: int = 0) -> str:
        """
        Publish message to queue with retry mechanism and DLQ support.
        
        Args:
            queue_name: Target queue name
            command: Message command type
            payload: Message payload
            correlation_id: Optional correlation ID for tracing
            retry_count: Current retry attempt count
            
        Returns:
            Generated correlation ID
        """
        if not self.channel:
            self.connect()
        
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())
        
        message = {
            'command': command,
            'payload': payload,
            'timestamp': datetime.utcnow().isoformat(),
            'correlation_id': correlation_id,
            'retry_count': retry_count
        }
        
        try:
            if self.channel is None:
                raise NetworkError("Channel not connected. Call connect() first.")
            
            # Setup DLX and DLQ for the queue
            self._setup_dlx_and_dlq(queue_name)
            
            # Declare queue with Dead Letter Exchange configuration
            self.channel.queue_declare(
                queue=queue_name, 
                durable=True,
                arguments={
                    'x-dead-letter-exchange': 'dlx_exchange',
                    'x-dead-letter-routing-key': f'{queue_name}.dlq'
                }
            )
            
            message_body = json.dumps(message)
            
            # If retry count exceeds max_retries, route directly to DLQ
            if retry_count >= self.max_retries:
                dlq_name = f'{queue_name}.dlq'
                self.channel.basic_publish(
                    exchange='dlx_exchange',
                    routing_key=dlq_name,
                    body=message_body,
                    properties=pika.BasicProperties(delivery_mode=2)
                )
                self.logger.warning(f"Message routed to DLQ after {retry_count} attempts: queue='{dlq_name}', command='{command}', correlation_id='{correlation_id}'")
            else:
                # Normal publish to primary queue
                self.channel.basic_publish(
                    exchange='',
                    routing_key=queue_name,
                    body=message_body,
                    properties=pika.BasicProperties(delivery_mode=2)  # Make message persistent
                )
                self.logger.debug(f"Published message to queue '{queue_name}': command='{command}', correlation_id='{correlation_id}', retry_count={retry_count}, payload_size={len(message_body)} bytes")
            
            return correlation_id
        except Exception as e:
            self.logger.error(f"Failed to publish message to queue '{queue_name}': command='{command}', correlation_id='{correlation_id}', retry_count={retry_count}, error: {e}")
            raise NetworkError(f"Failed to publish message: {e}")
    
    def consume_messages(self, queue_name: str, callback: Callable[[Dict[str, Any], str], None]):
        """
        Start consuming messages from queue with improved error handling and DLQ support.
        
        Args:
            queue_name: Queue to consume from
            callback: Function to handle received messages (message_data, correlation_id)
        """
        if not self.channel:
            self.connect()
        
        def message_handler(ch, method, properties, body):
            message = None
            correlation_id = 'unknown'
            
            try:
                message = json.loads(body)
                correlation_id = message.get('correlation_id', 'unknown')
                retry_count = message.get('retry_count', 0)
                
                # Call the callback function
                callback(message, correlation_id)
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
            except json.JSONDecodeError as e:
                body_preview = body[:100] if len(body) > 100 else body
                self.logger.error(f"Failed to decode JSON message from queue '{queue_name}': {e}. Body preview: {body_preview}")
                # Route malformed messages directly to DLQ (no retry)
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                
            except Exception as e:
                self.logger.error(f"Error processing message from queue '{queue_name}' (correlation_id: {correlation_id}): {e}")
                
                if message:
                    retry_count = message.get('retry_count', 0)
                    if retry_count < self.max_retries:
                        # Retry the message by republishing with incremented retry_count
                        try:
                            self.publish_message(
                                queue_name, 
                                message.get('command', 'unknown'),
                                message.get('payload', {}),
                                correlation_id,
                                retry_count + 1
                            )
                            self.logger.info(f"Retrying message: correlation_id='{correlation_id}', retry_count={retry_count + 1}")
                        except Exception as retry_e:
                            self.logger.error(f"Failed to retry message (correlation_id: {correlation_id}): {retry_e}")
                    else:
                        self.logger.warning(f"Message exceeded max retries, routing to DLQ: correlation_id='{correlation_id}', retry_count={retry_count}")
                
                # Acknowledge the original message to remove it from the queue
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        if self.channel is None:
            raise NetworkError("Channel not connected. Call connect() first.")
        
        # Setup DLX and DLQ for the queue
        self._setup_dlx_and_dlq(queue_name)
        
        # Declare queue with Dead Letter Exchange configuration
        self.channel.queue_declare(
            queue=queue_name, 
            durable=True,
            arguments={
                'x-dead-letter-exchange': 'dlx_exchange',
                'x-dead-letter-routing-key': f'{queue_name}.dlq'
            }
        )
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(queue=queue_name, on_message_callback=message_handler)
        
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            self.channel.stop_consuming()
    
    def close(self) -> None:
        """Close connection to RabbitMQ."""
        if self.connection and not self.connection.is_closed:
            self.connection.close()


class MessageBroker:
    """
    Consolidated message broker providing both publish and consume functionality.
    
    This class replaces the separate MessagePublisher and MessageConsumer classes
    to reduce code duplication and provide a unified interface.
    """
    
    def __init__(self, connection_params: Dict[str, Any], config: Optional[Dict[str, Any]] = None, db_manager=None):
        """
        Initialize message broker.
        
        Args:
            connection_params: RabbitMQ connection parameters (e.g., {'url': 'amqp://...'})
            config: Configuration dict containing messaging settings
            db_manager: Database manager instance for logging (optional)
        """
        self.connection_params = connection_params
        self.message_queue: Optional[MessageQueue] = None
        self.logger = get_logger(__name__, db_manager)
        self.config = config or {}
        self.db_manager = db_manager
    
    def connect(self, max_retries: int = 3, base_delay: float = 1.0):
        """
        Establish connection to message broker with retry mechanism.
        
        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay for exponential backoff (seconds)
        """
        try:
            self.message_queue = MessageQueue(self.connection_params, self.config, self.db_manager)
            self.message_queue.connect(max_retries=max_retries, base_delay=base_delay)
        except NetworkError:
            # Re-raise NetworkError from MessageQueue
            raise
        except Exception as e:
            raise MessagingError(f"Failed to connect to message broker: {e}")
    
    def publish(self, queue_name: str, command: str, payload: Dict[str, Any], 
                correlation_id: Optional[str] = None, retry_count: int = 0) -> str:
        """
        Publish message to queue with standardized signature and retry support.
        
        Args:
            queue_name: Target queue name
            command: Message command type
            payload: Message payload
            correlation_id: Optional correlation ID for tracing
            retry_count: Current retry attempt count
            
        Returns:
            Correlation ID (generated if not provided)
        """
        if not self.message_queue:
            self.connect()
        
        if self.message_queue is None:
            raise NetworkError("Failed to connect to message queue")
        
        return self.message_queue.publish_message(queue_name, command, payload, correlation_id, retry_count)
    
    def consume(self, queue_name: str, callback: Callable[[Dict[str, Any], str], None]):
        """
        Start consuming messages from queue with standardized callback interface.
        
        Args:
            queue_name: Queue to consume from
            callback: Message handler function that receives (message_data, correlation_id)
        """
        if not self.message_queue:
            self.connect()
        
        if self.message_queue is None:
            raise NetworkError("Failed to connect to message queue")
        
        self.message_queue.consume_messages(queue_name, callback)
    
    def close(self):
        """Close connection to message broker."""
        if self.message_queue:
            self.message_queue.close()

