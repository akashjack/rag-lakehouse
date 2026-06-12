# Kafka Consumers

A Kafka consumer reads records from topics and processes them.

## Consumer Groups

Consumers are organized into consumer groups. Each partition is consumed by exactly one consumer within a group, enabling parallel processing.

## Consumer Configuration

Key consumer configurations:
- `bootstrap.servers`: Kafka broker addresses
- `group.id`: Consumer group identifier
- `auto.offset.reset`: What to do when no offset exists (earliest/latest)
- `enable.auto.commit`: Whether to auto-commit offsets
- `max.poll.records`: Maximum records returned per poll

## Reading Messages

```java
Properties props = new Properties();
props.put("bootstrap.servers", "localhost:9092");
props.put("group.id", "my-group");
props.put("key.deserializer", "org.apache.kafka.common.serialization.StringDeserializer");
props.put("value.deserializer", "org.apache.kafka.common.serialization.StringDeserializer");

KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
consumer.subscribe(Arrays.asList("my-topic"));

while (true) {
    ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(100));
    for (ConsumerRecord<String, String> record : records) {
        System.out.printf("offset=%d, key=%s, value=%s%n",
            record.offset(), record.key(), record.value());
    }
}
```

## Offset Management

Offsets track which records have been consumed. They can be committed automatically or manually for fine-grained control over delivery guarantees.
