"""
Application Performance Monitoring (APM) integration using OpenTelemetry
"""

import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# Try to import optional exporters
try:
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    HAS_JAEGER = True
except ImportError:
    HAS_JAEGER = False

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    HAS_OTLP = True
except ImportError:
    HAS_OTLP = False


def setup_opentelemetry(
    service_name: str = "cfscraper-api",
    service_version: str = "1.0.0",
    environment: str = "development",
    jaeger_endpoint: Optional[str] = None,
    otlp_endpoint: Optional[str] = None
):
    """
    Setup OpenTelemetry tracing and metrics
    
    Args:
        service_name: Name of the service
        service_version: Version of the service
        environment: Environment (development, staging, production)
        jaeger_endpoint: Jaeger collector endpoint
        otlp_endpoint: OTLP collector endpoint
    """
    
    # Create resource with service information
    resource = Resource.create({
        "service.name": service_name,
        "service.version": service_version,
        "deployment.environment": environment,
    })
    
    # Setup tracing
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    
    # Setup span processors and exporters
    span_processors = []
    
    # Jaeger exporter
    if jaeger_endpoint and HAS_JAEGER:
        jaeger_exporter = JaegerExporter(
            agent_host_name=jaeger_endpoint.split("://")[1].split(":")[0],
            agent_port=int(jaeger_endpoint.split(":")[-1]) if ":" in jaeger_endpoint else 14268,
        )
        span_processors.append(BatchSpanProcessor(jaeger_exporter))
    
    # OTLP exporter
    if otlp_endpoint and HAS_OTLP:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        span_processors.append(BatchSpanProcessor(otlp_exporter))
    
    # Add span processors to tracer provider
    for processor in span_processors:
        tracer_provider.add_span_processor(processor)
    
    # Setup metrics with Prometheus reader
    prometheus_reader = PrometheusMetricReader()
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[prometheus_reader]
    )
    
    return tracer_provider, meter_provider


def instrument_fastapi(app, tracer_provider=None):
    """
    Instrument FastAPI application with OpenTelemetry
    
    Args:
        app: FastAPI application instance
        tracer_provider: Optional tracer provider
    """
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        excluded_urls="/health,/metrics,/ping"
    )


def instrument_database(engine=None):
    """
    Instrument SQLAlchemy database with OpenTelemetry
    
    Args:
        engine: SQLAlchemy engine (optional)
    """
    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        enable_commenter=True,
        commenter_options={}
    )


def instrument_redis():
    """Instrument Redis with OpenTelemetry"""
    RedisInstrumentor().instrument()


def instrument_http_clients():
    """Instrument HTTP clients with OpenTelemetry"""
    HTTPXClientInstrumentor().instrument()
    RequestsInstrumentor().instrument()


def setup_apm_from_env():
    """
    Setup APM from environment variables
    
    Environment variables:
        OTEL_SERVICE_NAME: Service name
        OTEL_SERVICE_VERSION: Service version
        OTEL_ENVIRONMENT: Environment
        JAEGER_ENDPOINT: Jaeger endpoint
        OTLP_ENDPOINT: OTLP endpoint
        ENABLE_APM: Enable APM (default: true)
    """
    if not os.getenv("ENABLE_APM", "true").lower() in ("true", "1", "yes"):
        return None, None
    
    service_name = os.getenv("OTEL_SERVICE_NAME", "cfscraper-api")
    service_version = os.getenv("OTEL_SERVICE_VERSION", "1.0.0")
    environment = os.getenv("OTEL_ENVIRONMENT", "development")
    jaeger_endpoint = os.getenv("JAEGER_ENDPOINT")
    otlp_endpoint = os.getenv("OTLP_ENDPOINT")
    
    return setup_opentelemetry(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        jaeger_endpoint=jaeger_endpoint,
        otlp_endpoint=otlp_endpoint
    )


def get_tracer(name: str = "cfscraper-api"):
    """
    Get a tracer instance
    
    Args:
        name: Tracer name
        
    Returns:
        Tracer instance
    """
    return trace.get_tracer(name)


class APMTracer:
    """Helper class for manual tracing"""
    
    def __init__(self, tracer_name: str = "cfscraper-api"):
        self.tracer = get_tracer(tracer_name)
    
    def start_span(self, name: str, **attributes):
        """
        Start a new span
        
        Args:
            name: Span name
            **attributes: Span attributes
            
        Returns:
            Span context manager
        """
        span = self.tracer.start_span(name)
        
        # Add attributes
        for key, value in attributes.items():
            span.set_attribute(key, value)
        
        return span
    
    def trace_function(self, name: str = None, **attributes):
        """
        Decorator to trace a function
        
        Args:
            name: Span name (defaults to function name)
            **attributes: Span attributes
        """
        def decorator(func):
            def wrapper(*args, **kwargs):
                span_name = name or f"{func.__module__}.{func.__name__}"
                
                with self.tracer.start_as_current_span(span_name) as span:
                    # Add attributes
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                    
                    try:
                        result = func(*args, **kwargs)
                        span.set_attribute("success", True)
                        return result
                    except Exception as e:
                        span.set_attribute("success", False)
                        span.set_attribute("error.type", type(e).__name__)
                        span.set_attribute("error.message", str(e))
                        span.record_exception(e)
                        raise
            
            return wrapper
        return decorator
    
    def trace_async_function(self, name: str = None, **attributes):
        """
        Decorator to trace an async function
        
        Args:
            name: Span name (defaults to function name)
            **attributes: Span attributes
        """
        def decorator(func):
            async def wrapper(*args, **kwargs):
                span_name = name or f"{func.__module__}.{func.__name__}"
                
                with self.tracer.start_as_current_span(span_name) as span:
                    # Add attributes
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                    
                    try:
                        result = await func(*args, **kwargs)
                        span.set_attribute("success", True)
                        return result
                    except Exception as e:
                        span.set_attribute("success", False)
                        span.set_attribute("error.type", type(e).__name__)
                        span.set_attribute("error.message", str(e))
                        span.record_exception(e)
                        raise
            
            return wrapper
        return decorator


# Global tracer instance
apm_tracer = APMTracer()


def setup_apm_instrumentation(app, database_engine=None):
    """
    Setup complete APM instrumentation
    
    Args:
        app: FastAPI application
        database_engine: SQLAlchemy engine
    """
    # Setup OpenTelemetry from environment
    tracer_provider, meter_provider = setup_apm_from_env()
    
    if tracer_provider is None:
        return  # APM disabled
    
    # Instrument FastAPI
    instrument_fastapi(app, tracer_provider)
    
    # Instrument database
    if database_engine:
        instrument_database(database_engine)
    
    # Instrument Redis
    instrument_redis()
    
    # Instrument HTTP clients
    instrument_http_clients()
    
    return tracer_provider, meter_provider
