"""A file to support reading/managing JSON-LD formatted data"""
from datetime import datetime
import json
from typing import Any

import pika
import httpx
import redis
import redis.exceptions
from pika.exceptions import AMQPConnectionError, UnroutableError
from rdflib import Graph
from tqdm import tqdm
import xmltodict

from hml_reader.schemas.weather import HML
from hml_reader.settings import Settings

settings = Settings()

def fetch_weather_products(headers) -> list[Any]:
    url = "https://api.weather.gov/products"
    headers = {
        'Accept': 'application/ld+json',
        'User-Agent': '(water.noaa.gov, user@rtx.com)'
    }
    
    params = {
        'type': 'HML'
    }

    timeout_config = httpx.Timeout(
        connect=5.0,
        read=30.0,
        write=5.0,
        pool=5.0
    )
    
    limits_config = httpx.Limits(
        max_keepalive_connections=5,
        max_connections=10,
        keepalive_expiry=30.0
    )
    
    with httpx.Client(timeout=timeout_config, limits=limits_config) as client:
        response = client.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            response_json = response.json()
            response_json['@context']["@version"] = float(response_json['@context']["@version"])
            
            data = json.dumps(response_json)
            g = Graph()
            g.parse(data=data, format='json-ld')
            data_dict = xmltodict.parse(g.serialize(format="pretty-xml"))
            return data_dict['rdf:RDF']['rdf:Description']
        else:
            raise httpx.HTTPError(f"Error fetching data: {response.status_code}")


def publish(channel, hml, settings) -> None:
    if not channel:
        raise RuntimeError(
            "Message could not be sent as there is no RabbitMQ Connection"
        )
    
    msg = hml.model_dump_json().encode()
    try:
        channel.basic_publish(
            exchange='',
            routing_key=settings.flooded_data_queue,
            body=msg,
            properties=pika.BasicProperties(
                delivery_mode=2,
            ),
            mandatory=True
        )
    except UnroutableError as e:
        raise RuntimeError("Message rejected") from e
                

def fetch_data() -> None:
    try:
        connection = pika.BlockingConnection(settings.connection_params)
        channel = connection.channel()
        channel.queue_declare(
            queue=settings.flooded_data_queue,
            durable=True
        )
    except AMQPConnectionError as e:
        print(f"RabbitMQ connection error: {e}")
        raise RuntimeError("Cannot connect to RabbitMQ service") from e
    print("Successfully connected to RabbitMQ")
    headers = {
        'Accept': 'application/ld+json',
        'User-Agent': '(water.noaa.gov, user@rtx.com)'
    }
    hml_data = fetch_weather_products(headers)
    try:
        r = redis.Redis(
            host=settings.redis_url,
            port=settings.redis_port,
            decode_responses=True
        )
        hml_data = sorted(hml_data, key=lambda x: datetime.fromisoformat(x["issuanceTime"]))
        for hml in tqdm(hml_data, desc="reading through api.weather.gov HML outputs"):
            hml_id = hml["id"]
            if r.get(hml_id) is None:
                hml_obj = HML(**hml)
                publish(channel, hml_obj, settings)
                r.set(hml_id, hml_obj.model_dump_json())
                r.expire(hml_id, 604800)  # exires after a week
    except redis.exceptions.ConnectionError as e:
        raise e("Cannot run Redis service") 
    connection.close()
    