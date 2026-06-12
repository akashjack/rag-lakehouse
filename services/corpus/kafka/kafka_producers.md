# Kafka Producers

A Kafka producer is a client that publishes records to Kafka topics.

## Producer Configuration

Key producer configurations:
- `bootstrap.servers`: List of Kafka broker addresses
- `key.serializer`: Serializer for the record key
- `value.serializer`: Serializer for the record value
- `acks`: Number of acknowledgments required (0, 1, or all)
- `retries`: Number of retry attempts on failure
- `batch.size`: Size of batches in bytes
- `linger.ms`: Time to wait before sending a batch

## Sending Messages

```java
Properties props = new Properties();
props.put("bootstrap.servers", "localhost:9092");
props.put("key.serializer", "org.apache.kafka.common.serialization.StringSerializer");
props.put("value.serializer", "org.apache.kafka.common.serialization.StringSerializer");

Producer<String, String> producer = new KafkaProducer<>(props);
producer.send(new ProducerRecord<>("my-topic", "key", "value"));
producer.close();
```

## Delivery Guarantees

- **At most once**: acks=0, messages may be lost
- **At least once**: acks=all with retries, messages may be duplicated
- **Exactly once**: Use idempotent producers and transactions
