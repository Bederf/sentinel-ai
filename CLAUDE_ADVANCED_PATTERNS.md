# CLAUDE_ADVANCED_PATTERNS.md

Companion guide for CLAUDE.md - Deep dives into advanced topics, patterns, and optimization strategies for SENTINEL BMS Intelligence Platform.

## Table of Contents

1. [Advanced Resilience Patterns](#advanced-resilience-patterns)
2. [ML Model Training & Inference](#ml-model-training--inference)
3. [RAG Integration Architecture](#rag-integration-architecture)
4. [Supabase Migration Strategies](#supabase-migration-strategies)
5. [Performance Optimization](#performance-optimization)
6. [MCP Tool Development](#mcp-tool-development)
7. [Testing Complex Scenarios](#testing-complex-scenarios)

---

## Advanced Resilience Patterns

### Circuit Breaker Deep Dive

The circuit breaker pattern prevents cascading failures by monitoring call patterns and "breaking" the circuit when failures exceed thresholds.

**State Machine:**

```python
# CLOSED → OPEN → HALF_OPEN → CLOSED

class CircuitBreakerState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery
```

**Implementation patterns:**

```python
# Pattern 1: Context manager for automatic state management
from app.utils.resilience import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=HttpError
)

async def call_external_api():
    async with breaker:
        response = await external_api.call()
        return response

# Pattern 2: Decorator for route handlers
from app.utils.resilience import circuit_breaker_decorator

@router.get("/api/external-data")
@circuit_breaker_decorator(failure_threshold=3)
async def fetch_external_data():
    return await external_service.get_data()

# Pattern 3: Manual state checking (advanced scenarios)
if breaker.is_open():
    # Serve stale data or return cached response
    return await cache.get_fallback()
else:
    async with breaker:
        return await fresh_data()
```

**Monitoring circuit breaker state:**

```bash
# Health endpoint includes circuit breaker metrics
curl http://localhost:9095/api/system/health | jq '.components.circuit_breaker'

# Output:
{
  "status": "healthy",
  "state": "CLOSED",
  "failure_count": 0,
  "success_count": 42,
  "last_failure_time": null,
  "recovery_attempts": 0
}
```

**Common patterns in codebase:**

- **MRI Evolution API:** Uses circuit breaker with 5-failure threshold, 60s recovery timeout
- **Supabase connection:** Uses circuit breaker to gracefully fallback to JSON storage
- **Device manager:** Uses circuit breaker for BACnet/Modbus communication

### Rate Limiter Fine-Tuning

Rate limiting prevents API throttling and ensures fair resource allocation:

```python
# Typical configuration
from app.config.settings import RATE_LIMIT_CALLS, RATE_LIMIT_PERIOD

# MRI Evolution: 200 calls per 60 seconds
rate_limiter = RateLimiter(calls=200, period=60)

# Device manager: 1000 calls per 60 seconds (local, no external limits)
device_limiter = RateLimiter(calls=1000, period=60)

# Per-user rate limiting (optional)
per_user_limiter = RateLimiter(calls=100, period=60, per_key=True)
```

**Advanced usage:**

```python
# Priority-based rate limiting
async def high_priority_request():
    # Skip rate limiting for critical operations
    if is_critical():
        return await perform_action()

    # Otherwise, respect rate limit
    await rate_limiter.acquire()
    return await perform_action()

# Dynamic rate limit adjustment
def adjust_rate_limit(error_response):
    """Adjust rate limit based on API response headers"""
    remaining = int(error_response.headers.get('X-RateLimit-Remaining', 0))
    reset_time = int(error_response.headers.get('X-RateLimit-Reset', 0))

    if remaining < 10:
        rate_limiter.throttle(multiplier=0.5)
    elif remaining > 100:
        rate_limiter.throttle(multiplier=1.0)
```

### Deduplication Strategies

Prevents alert storms and duplicate work orders:

```python
# 30-minute cooldown per equipment
deduplicator = RequestDeduplicator(cooldown_seconds=1800)

# Check before creating work order
async def create_work_order(equipment_id, anomaly):
    key = f"work_order:{equipment_id}"

    if deduplicator.is_duplicate(key):
        logger.info(f"Skipping duplicate WO for {equipment_id}")
        return {"status": "duplicate", "cooldown_remaining": deduplicator.get_cooldown(key)}

    # Record this request
    deduplicator.record(key)

    # Create work order
    return await workorder_service.create(equipment_id, anomaly)

# Per-site deduplication (different cooldown)
site_deduplicator = RequestDeduplicator(cooldown_seconds=300)  # 5 min

async def handle_site_alert(site_id, alert_type):
    key = f"{site_id}:{alert_type}"

    if site_deduplicator.is_duplicate(key):
        return  # Skip if already alerted in past 5 min

    site_deduplicator.record(key)
    await send_alert(site_id, alert_type)
```

---

## ML Model Training & Inference

### LSTM Model Training Workflow

**Training an LSTM model for equipment anomaly detection:**

```bash
# Basic training
cd backend && source venv/bin/activate
python -m ml.lstm.train \
  --equipment-type chiller \
  --epochs 50 \
  --batch-size 32 \
  --validation-split 0.2

# Advanced options
python -m ml.lstm.train \
  --equipment-type chiller \
  --epochs 100 \
  --batch-size 16 \
  --learning-rate 0.001 \
  --dropout 0.2 \
  --look-back 24 \
  --output-dir ./models/custom
```

**Custom training script:**

```python
# backend/ml/lstm/custom_train.py
from ml.lstm.trainer import LSTMTrainer
from ml.lstm.data_loader import load_equipment_data

async def train_custom_model():
    # Load data
    data = await load_equipment_data(
        equipment_type='chiller',
        time_range_days=180,
        normalize=True
    )

    # Initialize trainer
    trainer = LSTMTrainer(
        input_shape=(24, 5),  # 24 timesteps, 5 features
        hidden_units=[64, 32],
        dropout=0.2
    )

    # Train
    history = await trainer.train(
        data['X_train'],
        data['y_train'],
        validation_data=(data['X_val'], data['y_val']),
        epochs=100,
        batch_size=32
    )

    # Save model
    await trainer.save('./models/chiller_lstm_v2.h5')

    # Evaluate
    metrics = await trainer.evaluate(data['X_test'], data['y_test'])
    print(f"Test MSE: {metrics['mse']:.6f}")
    print(f"Test MAE: {metrics['mae']:.4f}")
```

### Autoencoder for Anomaly Detection

**Autoencoder training for multivariate anomaly detection:**

```python
# backend/ml/autoencoder/train.py
from ml.autoencoder.model import AutoEncoder
from ml.autoencoder.data import load_normal_data

async def train_anomaly_detector():
    # Load only "normal" operational data
    X_train = await load_normal_data(
        equipment_type='chiller',
        days=90
    )

    # Initialize autoencoder
    ae = AutoEncoder(
        input_dim=10,  # 10 sensor features
        encoding_dim=3
    )

    # Train (unsupervised)
    history = await ae.train(
        X_train,
        epochs=50,
        batch_size=32,
        validation_split=0.2
    )

    # Calculate reconstruction error threshold
    train_predictions = ae.predict(X_train)
    train_mse = np.mean(np.power(X_train - train_predictions, 2), axis=1)
    threshold = np.percentile(train_mse, 95)  # 95th percentile

    print(f"Anomaly threshold (MSE): {threshold:.6f}")

    # Save model and threshold
    await ae.save('./models/chiller_ae.h5')
    with open('./models/chiller_ae_threshold.json', 'w') as f:
        json.dump({'threshold': float(threshold)}, f)
```

**Using trained models for inference:**

```python
# backend/app/services/anomaly_detection_service.py
from ml.lstm.inference import LSTMInference
from ml.autoencoder.inference import AutoEncoderInference

class AnomalyDetectionService:
    async def __init__(self):
        # Load pre-trained models
        self.lstm = await LSTMInference.load('./models/chiller_lstm.h5')
        self.ae = await AutoEncoderInference.load('./models/chiller_ae.h5')

        # Load thresholds
        with open('./models/chiller_ae_threshold.json') as f:
            self.ae_threshold = json.load(f)['threshold']

    async def detect_anomalies(self, sensor_data):
        """
        Dual detection: LSTM for trend anomalies, AE for multivariate anomalies
        """
        results = {
            'lstm_anomaly': False,
            'ae_anomaly': False,
            'confidence': 0.0,
            'details': {}
        }

        # LSTM: Predict next value, check if actual deviates significantly
        lstm_pred = await self.lstm.predict(sensor_data[-24:])  # Last 24 hours
        lstm_error = abs(sensor_data[-1] - lstm_pred)
        results['lstm_anomaly'] = lstm_error > 2.0  # Threshold: 2 std devs
        results['details']['lstm_error'] = float(lstm_error)

        # Autoencoder: Check reconstruction error
        ae_pred = await self.ae.predict(sensor_data)
        ae_error = np.mean(np.power(sensor_data - ae_pred, 2))
        results['ae_anomaly'] = ae_error > self.ae_threshold
        results['details']['ae_error'] = float(ae_error)

        # Confidence = both models agree
        if results['lstm_anomaly'] and results['ae_anomaly']:
            results['confidence'] = 0.95  # High confidence
        elif results['lstm_anomaly'] or results['ae_anomaly']:
            results['confidence'] = 0.60  # Medium confidence
        else:
            results['confidence'] = 0.0

        return results
```

---

## RAG Integration Architecture

### Knowledge Base Ingest

**Adding documents to RAG knowledge base:**

```python
# backend/scripts/ingest_rag_knowledge.py
import asyncio
from app.services.rag_service import RAGService

async def ingest_knowledge():
    rag = RAGService()

    # Ingest maintenance manuals
    documents = [
        {
            'id': 'chiller_maintenance_guide',
            'title': 'Chiller Maintenance Guide',
            'content': open('./docs/chiller_guide.md').read(),
            'metadata': {'equipment_type': 'chiller', 'priority': 'high'}
        },
        {
            'id': 'vav_troubleshooting',
            'title': 'VAV Troubleshooting',
            'content': open('./docs/vav_troubleshooting.md').read(),
            'metadata': {'equipment_type': 'vav', 'priority': 'medium'}
        }
    ]

    for doc in documents:
        await rag.ingest_document(
            doc_id=doc['id'],
            title=doc['title'],
            content=doc['content'],
            metadata=doc['metadata']
        )

    print(f"Ingested {len(documents)} documents")

# Run ingestion
if __name__ == '__main__':
    asyncio.run(ingest_knowledge())
```

### Using RAG in Chat Context

**Retrieving relevant documents for AI chat:**

```python
# backend/app/services/chat_service.py
class ChatService:
    async def answer_question(self, user_question, equipment_code):
        # Retrieve relevant documents from knowledge base
        relevant_docs = await self.rag_service.retrieve(
            query=user_question,
            equipment_type=self._get_equipment_type(equipment_code),
            top_k=3  # Get top 3 relevant documents
        )

        # Build context for AI model
        context = "\n".join([
            f"Documentation: {doc['title']}\n{doc['content'][:500]}..."
            for doc in relevant_docs
        ])

        # Generate answer using retrieved context
        prompt = f"""
        Answer the following question about {equipment_code} based on the documentation:

        Question: {user_question}

        Relevant Documentation:
        {context}

        Answer:
        """

        response = await self.ai_service.query(prompt)

        return {
            'answer': response,
            'sources': [doc['title'] for doc in relevant_docs],
            'confidence': len(relevant_docs) / 3  # Confidence based on sources found
        }
```

---

## Supabase Migration Strategies

### Complex Migration Pattern: Adding Constraints & Functions

**Example: Adding computed health scores with triggers:**

```sql
-- backend/supabase/migrations/XXX_equipment_health_triggers.sql

-- 1. Add computed column
ALTER TABLE equipment ADD COLUMN health_score DECIMAL(3,2) GENERATED ALWAYS AS (
  CASE
    WHEN maintenance_due_days < 7 THEN 0.3
    WHEN maintenance_due_days < 14 THEN 0.5
    WHEN age_years > 10 THEN 0.6
    ELSE 0.9
  END
) STORED;

-- 2. Create function to recalculate
CREATE OR REPLACE FUNCTION recalculate_health_score(p_equipment_id UUID)
RETURNS DECIMAL(3,2) AS $$
DECLARE
    v_score DECIMAL(3,2);
BEGIN
    SELECT
        COALESCE(health_score, 0.5) INTO v_score
    FROM equipment
    WHERE id = p_equipment_id;

    RETURN v_score;
END;
$$ LANGUAGE plpgsql;

-- 3. Create trigger for updates
CREATE TRIGGER health_score_update
AFTER UPDATE ON maintenance_records
FOR EACH ROW
EXECUTE FUNCTION recalculate_health_score(NEW.equipment_id);

-- 4. Add RLS policy for read access
CREATE POLICY "Users can view equipment health scores"
ON equipment FOR SELECT
USING (true);
```

### Migration Testing Pattern

**Validate migrations locally before deploying:**

```bash
# Start local Supabase with reset
supabase stop
supabase start

# Run migrations in sequence
supabase migration list
supabase migration repair <migration-name>  # If conflicts

# Verify schema
supabase db pull  # Compare with local schema

# Test with sample data
psql $DATABASE_URL < tests/fixtures/sample_data.sql

# Validate queries
psql $DATABASE_URL -c "SELECT COUNT(*) FROM equipment;"
```

---

## Performance Optimization

### Database Query Optimization

**Identifying slow queries:**

```python
# backend/app/middleware/query_logger.py
import time

@app.middleware("http")
async def log_slow_queries(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    if duration > 0.5:  # Log queries taking >500ms
        logger.warning(
            f"Slow query: {request.method} {request.url.path}",
            extra={'duration_ms': duration * 1000}
        )

    return response
```

**Optimization techniques:**

```python
# WRONG: N+1 queries
async def get_buildings_with_equipment():
    buildings = await building_repo.get_all()
    for building in buildings:
        building.equipment = await equipment_repo.get_by_building(building.id)
    return buildings

# CORRECT: Join query
async def get_buildings_with_equipment():
    return await db.query("""
        SELECT b.*, json_agg(e.*) as equipment
        FROM buildings b
        LEFT JOIN equipment e ON b.id = e.building_id
        GROUP BY b.id
    """)

# CORRECT: Batch queries
async def get_buildings_with_equipment():
    buildings = await building_repo.get_all()
    building_ids = [b.id for b in buildings]
    equipment_map = await equipment_repo.get_by_buildings(building_ids)

    for building in buildings:
        building.equipment = equipment_map.get(building.id, [])
    return buildings
```

### Caching Strategy

**Multi-level caching:**

```python
# Level 1: Application-level cache (Redis)
# Level 2: Repository-level cache (in-memory dict)
# Level 3: Database query

class CachedEquipmentRepository:
    async def get_by_code(self, code: str) -> Equipment:
        # L1: Check Redis
        cached = await redis.get(f"equipment:{code}")
        if cached:
            return Equipment(**cached)

        # L2: Check memory cache (5-minute TTL)
        if code in self._memory_cache:
            return self._memory_cache[code]

        # L3: Query database
        equipment = await db.query(
            "SELECT * FROM equipment WHERE code = $1",
            code
        )

        # Populate caches
        await redis.set(f"equipment:{code}", equipment.dict(), ttl=300)
        self._memory_cache[code] = equipment

        return equipment
```

### API Response Optimization

**Pagination and field selection:**

```python
# ROUTE: Get equipment with optional field selection
@router.get("/api/equipment")
async def list_equipment(
    skip: int = 0,
    limit: int = 20,
    fields: str = "id,code,name,building_id"  # Request only needed fields
):
    # Parse field selection
    field_list = fields.split(',')

    # Query with selected fields only
    equipment = await equipment_repo.get_paginated(
        skip=skip,
        limit=limit,
        fields=field_list
    )

    return {
        'items': equipment,
        'total': await equipment_repo.count(),
        'page': skip // limit,
        'page_size': limit
    }
```

---

## MCP Tool Development

### Adding a New MCP Tool

**Complete example: Adding "predict_maintenance" tool:**

```python
# 1. Define tool in backend/app/mcp/tool_definitions.py
PREDICT_MAINTENANCE_TOOL = {
    "name": "predict_maintenance",
    "description": "Predict maintenance requirements for equipment",
    "inputSchema": {
        "type": "object",
        "properties": {
            "equipment_code": {
                "type": "string",
                "description": "Equipment ID (e.g., S002-CHILLER-B1-001)"
            },
            "days_ahead": {
                "type": "number",
                "description": "Number of days to predict ahead (default: 30)"
            }
        },
        "required": ["equipment_code"]
    }
}

# 2. Implement handler in backend/app/mcp/tools/predict_maintenance.py
async def predict_maintenance(equipment_code: str, days_ahead: int = 30) -> dict:
    """
    Predict maintenance requirements for equipment
    """
    # Get equipment
    equipment = await equipment_repo.get_by_code(equipment_code)
    if not equipment:
        raise ValueError(f"Equipment not found: {equipment_code}")

    # Get historical data
    history = await anomaly_repo.get_history(
        equipment_code=equipment_code,
        days=90
    )

    # Run ML model
    predictions = await ml_service.predict_maintenance(
        equipment=equipment,
        history=history,
        days_ahead=days_ahead
    )

    return {
        "equipment_code": equipment_code,
        "predicted_maintenance": predictions,
        "confidence": predictions.get('confidence', 0.0),
        "recommendation": generate_recommendation(predictions)
    }

# 3. Register in backend/app/mcp/simbiot_server.py
tools = [
    PREDICT_MAINTENANCE_TOOL,
    # ... other tools
]

async def handle_tool_call(tool_name: str, tool_input: dict):
    if tool_name == "predict_maintenance":
        return await predict_maintenance(**tool_input)
    # ... other tools

# 4. Test locally
# backend/tests/mcp/test_predict_maintenance.py
async def test_predict_maintenance():
    result = await predict_maintenance(
        equipment_code="S002-CHILLER-B1-001",
        days_ahead=30
    )

    assert result['equipment_code'] == "S002-CHILLER-B1-001"
    assert 'predicted_maintenance' in result
    assert 0 <= result['confidence'] <= 1
```

---

## Testing Complex Scenarios

### Integration Test: Full Lifecycle

**Testing the complete anomaly → work order → feedback → health update cycle:**

```python
# backend/tests/integration/test_full_lifecycle.py
import pytest
from app.services.lifecycle_orchestrator import LifecycleOrchestrator

@pytest.mark.integration
async def test_anomaly_to_maintenance_feedback_cycle():
    """Test full cycle: anomaly detection → WO → feedback → health update"""

    orchestrator = LifecycleOrchestrator()
    equipment_code = "S002-CHILLER-B1-001"

    # 1. Inject anomaly
    anomaly = SentinelAnomaly(
        source=AnomalySource.BMS_ANOMALY,
        equipment_code=equipment_code,
        severity_score=0.82,
        summary="Discharge temp rising"
    )

    # 2. Detect anomaly
    result = await orchestrator.process_anomaly(anomaly)
    assert result['status'] == 'work_order_created'
    work_order_id = result['work_order_id']

    # 3. Simulate technician accepting and completing WO
    await orchestrator.update_work_order_status(
        work_order_id=work_order_id,
        status='in_progress',
        technician_id='tech_001'
    )

    # 4. Provide service feedback
    feedback = ServiceFeedback(
        work_order_id=work_order_id,
        equipment_code=equipment_code,
        resolution_type='compressor_maintenance',
        issue_found=True,
        corrective_action='Replaced compressor oil',
        health_impact=HealthImpact.POSITIVE
    )

    updated_health = await orchestrator.record_feedback(feedback)

    # 5. Verify health improved
    equipment = await equipment_repo.get_by_code(equipment_code)
    assert equipment.health_score > 0.7  # Should improve significantly

    # 6. Verify maintenance history updated
    maintenance_records = await maintenance_repo.get_by_equipment(equipment_code)
    assert len(maintenance_records) > 0
```

### Load Testing Script

**Using k6 for performance testing:**

```javascript
// k6/scenarios/equipment_load_test.js
import http from 'k8n/http';
import { check, sleep } from 'k6';

export let options = {
  stages: [
    { duration: '2m', target: 100 },   // Ramp up to 100 users
    { duration: '5m', target: 100 },   // Stay at 100
    { duration: '2m', target: 200 },   // Ramp to 200
    { duration: '5m', target: 200 },   // Stay at 200
    { duration: '2m', target: 0 },     // Ramp down
  ],
};

export default function() {
  // Test: List equipment
  let resp = http.get('http://localhost:9095/api/equipment?limit=20');
  check(resp, {
    'list equipment status 200': (r) => r.status === 200,
    'list equipment response time < 200ms': (r) => r.timings.duration < 200,
  });

  sleep(1);

  // Test: Get equipment details
  resp = http.get('http://localhost:9095/api/equipment/S002-CHILLER-B1-001');
  check(resp, {
    'get equipment status 200': (r) => r.status === 200,
    'get equipment response time < 100ms': (r) => r.timings.duration < 100,
  });

  sleep(1);
}
```

**Run load test:**

```bash
cd k6 && k6 run scenarios/equipment_load_test.js --out json=results.json
```

---

## Summary

This advanced patterns guide provides:

- **Resilience strategies** for production robustness
- **ML workflows** for model training and inference
- **RAG patterns** for knowledge integration
- **Database optimization** techniques
- **Performance tuning** strategies
- **MCP tool development** complete examples
- **Integration testing** approaches

For implementation details, reference:
- `backend/app/utils/resilience.py` — Resilience utilities
- `backend/ml/` — ML model implementations
- `backend/app/services/rag_service.py` — RAG service
- `backend/app/mcp/` — MCP server and tools

---

*For general guidance, see CLAUDE.md. For specific implementations, see code comments and inline documentation.*
