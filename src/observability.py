import logging
import watchtower
import boto3
from src.config import settings

def setup_cloudwatch_logging():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("queryforce")
    
    if settings.AWS_REGION:
        boto3_session = boto3.Session(region_name=settings.AWS_REGION)
        cw_handler = watchtower.CloudWatchLogHandler(
            boto3_session=boto3_session,
            log_group="queryforce",
            stream_name="api"
        )
        logger.addHandler(cw_handler)
    
    return logger

logger = setup_cloudwatch_logging()

def put_metric(metric_name: str, value: float = 1.0, unit: str = 'Count'):
    if settings.AWS_REGION:
        try:
            client = boto3.client('cloudwatch', region_name=settings.AWS_REGION)
            client.put_metric_data(
                Namespace='QueryForce',
                MetricData=[
                    {
                        'MetricName': metric_name,
                        'Value': value,
                        'Unit': unit
                    },
                ]
            )
        except Exception as e:
            logger.error(f"Failed to put metric {metric_name}: {e}")
