"""
Test script to verify UUID sampling from Weaviate Drupal API collection.

This script connects to Weaviate and samples UUIDs from the DrupalAPI
collection to verify data integrity.
"""
import logging
import sys
from pathlib import Path

# Add project root to sys.path using relative path from script location
# Script is in data/scraper, project root is three levels up
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from api_gateway.services.weaviate_connection import WeaviateConnection, DRUPAL_API_COLLECTION_NAME

logger = logging.getLogger(__name__)

try:
    with WeaviateConnection() as client:
        collection = client.collections.get(DRUPAL_API_COLLECTION_NAME)
        count = 0
        uuids = set()
        for obj in collection.iterator(include_vector=False):
            props = obj.properties
            if props and "uuid" in props:
                uuids.add(props["uuid"])
            count += 1
            if count >= 10:
                break
        logger.info(f"Sampled {count} objects, found {len(uuids)} UUIDs")
        logger.info(f"Sample UUIDs: {list(uuids)[:3]}")
except Exception as e:
    logger.error(f"Failed to query Weaviate: {e}")
    raise
