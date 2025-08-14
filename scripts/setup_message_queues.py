#!/usr/bin/env python3
"""
Message Queue Setup Script for MQI Communicator System

This script configures RabbitMQ queues, exchanges, and bindings
required for inter-service communication.
"""

import os
import sys
import argparse
import pika
from pika import exceptions

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.common.config_loader import load_config
from src.common.logger import get_logger

# Set up logging
logger = get_logger(__name__)


class MessageQueueSetup:
    """RabbitMQ setup and configuration manager."""
    
    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.connection = None
        self.channel = None
    
    def connect(self):
        """Establish connection to RabbitMQ server."""
        try:
            logger.info(f"Connecting to RabbitMQ: {self.rabbitmq_url}")
            self.connection = pika.BlockingConnection(
                pika.URLParameters(self.rabbitmq_url)
            )
            self.channel = self.connection.channel()
            logger.info("✓ Connected to RabbitMQ successfully")
        except exceptions.AMQPConnectionError as e:
            raise RuntimeError(f"Failed to connect to RabbitMQ: {e}")
    
    def setup_exchanges(self):
        """Create required exchanges."""
        logger.info("Creating exchanges...")
        
        exchanges = [
            ('mqi_direct', 'direct'),
            ('mqi_topic', 'topic'),
            ('mqi_fanout', 'fanout')
        ]
        
        for exchange_name, exchange_type in exchanges:
            self.channel.exchange_declare(
                exchange=exchange_name,
                exchange_type=exchange_type,
                durable=True
            )
            logger.info(f"  ✓ Exchange created: {exchange_name} ({exchange_type})")
    
    def setup_queues(self):
        """Create required queues for all workers."""
        logger.info("Creating queues...")
        
        # Define all worker queues with their properties
        queues = [
            # Conductor queues
            ('conductor_new_case', True, 'Events for new cases detected'),
            ('conductor_execution_result', True, 'Results from remote execution'),
            ('conductor_transfer_result', True, 'Results from file transfers'),
            
            # Case Scanner queues
            ('case_scanner_scan', True, 'Scan requests for new cases'),
            ('case_scanner_events', True, 'Case detection events'),
            
            # File Transfer queues
            ('file_transfer_upload', True, 'File upload requests'),
            ('file_transfer_download', True, 'File download requests'),
            ('file_transfer_results', True, 'File transfer results'),
            
            # Remote Executor queues
            ('remote_executor_commands', True, 'Remote command execution requests'),
            ('remote_executor_results', True, 'Command execution results'),
            
            # System Curator queues
            ('system_curator_monitor', True, 'System monitoring requests'),
            ('system_curator_status', True, 'System status updates'),
            
            # Archiver queues
            ('archiver_requests', True, 'Archive operation requests'),
            ('archiver_status', True, 'Archive operation status'),
            
            # Health monitoring queues
            ('health_monitor_check', True, 'Health check requests'),
            ('health_monitor_alerts', True, 'System health alerts'),
            
            # System-wide queues
            ('system_notifications', True, 'System-wide notifications'),
            ('error_notifications', True, 'Error and exception notifications')
        ]
        
        for queue_name, durable, description in queues:
            # Declare queue
            self.channel.queue_declare(
                queue=queue_name,
                durable=durable,
                arguments={
                    'x-message-ttl': 86400000,  # 24 hours TTL
                    'x-max-length': 10000       # Max 10k messages
                }
            )
            logger.info(f"  ✓ Queue created: {queue_name}")
            
            # Bind to direct exchange with routing key = queue name
            self.channel.queue_bind(
                exchange='mqi_direct',
                queue=queue_name,
                routing_key=queue_name
            )
    
    def setup_bindings(self):
        """Create queue bindings to exchanges."""
        logger.info("Setting up queue bindings...")
        
        # Topic exchange bindings for pattern-based routing
        topic_bindings = [
            ('conductor_new_case', 'case.new.*'),
            ('conductor_execution_result', 'execution.result.*'),
            ('conductor_transfer_result', 'transfer.result.*'),
            ('system_notifications', 'system.*'),
            ('error_notifications', 'error.*'),
            ('health_monitor_alerts', 'health.alert.*')
        ]
        
        for queue_name, routing_pattern in topic_bindings:
            self.channel.queue_bind(
                exchange='mqi_topic',
                queue=queue_name,
                routing_key=routing_pattern
            )
            logger.info(f"  ✓ Topic binding: {queue_name} -> {routing_pattern}")
        
        # Fanout bindings for broadcast messages
        broadcast_queues = [
            'system_notifications',
            'health_monitor_check'
        ]
        
        for queue_name in broadcast_queues:
            self.channel.queue_bind(
                exchange='mqi_fanout',
                queue=queue_name
            )
            logger.info(f"  ✓ Fanout binding: {queue_name}")
    
    def setup_dead_letter_queues(self):
        """Create dead letter queues for failed messages."""
        logger.info("Setting up dead letter queues...")
        
        # Dead letter exchange
        self.channel.exchange_declare(
            exchange='mqi_dlx',
            exchange_type='direct',
            durable=True
        )
        
        # Dead letter queue
        self.channel.queue_declare(
            queue='dead_letters',
            durable=True,
            arguments={
                'x-message-ttl': 604800000  # 7 days TTL for dead letters
            }
        )
        
        self.channel.queue_bind(
            exchange='mqi_dlx',
            queue='dead_letters',
            routing_key='#'
        )
        
        logger.info("  ✓ Dead letter exchange and queue created")
    
    def verify_setup(self):
        """Verify that all queues and exchanges are properly configured."""
        logger.info("Verifying message queue setup...")
        
        # Verify exchanges exist
        exchanges = ['mqi_direct', 'mqi_topic', 'mqi_fanout', 'mqi_dlx']
        for exchange in exchanges:
            try:
                self.channel.exchange_declare(
                    exchange=exchange,
                    exchange_type='direct',  # Type doesn't matter for passive declare
                    passive=True
                )
                logger.info(f"  ✓ Exchange verified: {exchange}")
            except exceptions.ChannelClosedByBroker:
                logger.error(f"  ❌ Exchange missing: {exchange}")
                self.channel = self.connection.channel()  # Reopen channel
        
        # Verify a few key queues exist
        key_queues = [
            'conductor_new_case',
            'remote_executor_commands',
            'file_transfer_upload',
            'dead_letters'
        ]
        
        for queue in key_queues:
            try:
                method = self.channel.queue_declare(queue=queue, passive=True)
                message_count = method.method.message_count
                logger.info(f"  ✓ Queue verified: {queue} ({message_count} messages)")
            except exceptions.ChannelClosedByBroker:
                logger.error(f"  ❌ Queue missing: {queue}")
                self.channel = self.connection.channel()  # Reopen channel
    
    def get_queue_stats(self):
        """Get statistics for all queues."""
        logger.info("Queue Statistics:")
        logger.info("-" * 40)
        
        try:
            # Use management API if available, otherwise basic info
            queues = [
                'conductor_new_case', 'remote_executor_commands',
                'file_transfer_upload', 'system_notifications'
            ]
            
            for queue in queues:
                try:
                    method = self.channel.queue_declare(queue=queue, passive=True)
                    message_count = method.method.message_count
                    consumer_count = method.method.consumer_count
                    logger.info(f"  {queue:25} Messages: {message_count:4d} Consumers: {consumer_count}")
                except Exception:
                    logger.warning(f"  {queue:25} Status: Unknown")
        except Exception as e:
            logger.error(f"Could not retrieve queue statistics: {e}")
    
    def close(self):
        """Close RabbitMQ connection."""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger.info("RabbitMQ connection closed")


def main():
    """Main message queue setup function."""
    parser = argparse.ArgumentParser(description="Setup MQI Communicator message queues")
    parser.add_argument('--env', choices=['development', 'production'], 
                       default='development', help='Environment to set up')
    parser.add_argument('--rabbitmq-url', help='Override RabbitMQ URL')
    parser.add_argument('--verify-only', action='store_true', 
                       help='Only verify existing setup')
    parser.add_argument('--stats', action='store_true', 
                       help='Show queue statistics')
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        if args.rabbitmq_url:
            rabbitmq_url = args.rabbitmq_url
        else:
            config_file = f"config.{args.env}.yaml"
            if not os.path.exists(os.path.join("config", config_file)):
                config_file = "config.default.yaml"
            
            config = load_config(os.path.join("config", config_file))
            rabbitmq_url = config['rabbitmq']['url']
        
        logger.info(f"Setting up message queues for {args.env} environment")
        
        # Initialize message queue setup
        mq_setup = MessageQueueSetup(rabbitmq_url)
        mq_setup.connect()
        
        if not args.verify_only:
            mq_setup.setup_exchanges()
            mq_setup.setup_queues()
            mq_setup.setup_bindings()
            mq_setup.setup_dead_letter_queues()
        
        mq_setup.verify_setup()
        
        if args.stats:
            mq_setup.get_queue_stats()
        
        mq_setup.close()
        
        logger.info(f"Message queue setup completed successfully for {args.env} environment")
        
    except Exception as e:
        logger.error(f"Message queue setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()