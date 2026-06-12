# Apache Kafka Overview

Apache Kafka is a distributed event streaming platform capable of handling trillions of events a day. Kafka is used for building real-time data pipelines and streaming applications.

## Core Concepts

### Topics
A topic is a category or feed name to which records are published. Topics in Kafka are always multi-subscriber — a topic can have zero, one, or many consumers that subscribe to the data written to it.

### Partitions
Topics are split into partitions. Each partition is an ordered, immutable sequence of records. Partitions allow Kafka to scale horizontally across multiple brokers.

### Producers
Producers publish data to topics. The producer is responsible for choosing which partition within a topic to publish to. This can be done round-robin or based on a key.

### Consumers
Consumers read data from topics. Each consumer belongs to a consumer group. Each record published to a topic is delivered to one consumer instance within each subscribing consumer group.

### Brokers
A Kafka cluster consists of one or more servers called brokers. Brokers handle all read and write requests from clients and replicate data across the cluster.

### ZooKeeper / KRaft
Kafka traditionally used ZooKeeper for cluster coordination. Kafka 3.0+ supports KRaft mode which removes the ZooKeeper dependency, simplifying deployment.

## Key Features

- **High throughput**: Kafka can handle millions of messages per second
- **Fault tolerance**: Data is replicated across multiple brokers
- **Scalability**: Horizontally scalable by adding brokers and partitions
- **Durability**: Messages are persisted to disk and replicated
- **Low latency**: Sub-millisecond latency for producers and consumers
