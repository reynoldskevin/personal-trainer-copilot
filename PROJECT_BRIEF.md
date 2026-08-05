# Knowledge Graph Coaching Platform

Fitness coaches spend too much time manually analyzing client context across generating workouts, and chatting with clients.

We need better context around injuries, goals, chats, biometrics, and transcripts. This makes it difficult to deliver truly hyper-personalized coaching at scale.

We are building an AI-native platform that uses a knowledge graph as a GraphRAG and LLMs to help coaches generate safer, smarter, and more personalized workout recommendations and coaching insights in real time.

## Problem & Context

### Business Context

This platform helps coaches do their jobs better by giving them AI-assisted context and recommendations for each client.

The system combines:
- workouts
- injuries
- goals
- adherence
- chat history
- transcripts
- biometrics
- longitudinal member data

The platform uses ontologies such as SNOMED CT inside a knowledge graph to reason about exercises, safety, injuries, and health relationships.

This is a core foundation for future AI coaching experiences across the platform.

### Impact Metrics

- Reduced coach operational time 
- Faster workout generation 
- Improved personalization quality 
- Increased member engagement 
- Reduced churn 
- Better coach efficiency 
- Improved retention and ROI

## Requirements & Success Criteria

### Functional Requirements

- Member profile ingestion
- Knowledge graph relationships
- Vector search / semantic retrieval
- AI-generated workout recommendations
- Injury-aware exercise filtering
- Chat/context-aware personalization
- Simple frontend dashboard or interface
- API endpoints for retrieval + generation

### Performance Benchmarks

- AI response time under 5 seconds
- Scalable architecture (start 100K nodes to hundred Ms)
- Clean retrieval quality
- Reasonable prompt/token efficiency

### Code Quality Expectations

- Strong project structure
- Clear documentation
- Evals
- Guardrails
- Readable code
- Typed APIs
- Dockerized local setup
- Git commits with meaningful history

## Technology

### Required Languages

Python

### AI / ML Frameworks

OpenAI API, LangChain, LangGraph, Vector embeddings, GraphRAG concepts, langFuse

### Dev Tools

AWS Bedrock AgentCore, React / Next.js, Docker, Git / GitHub

### Cloud Platforms

AWS 

### Other Requirements

- Neo4j or graph database experience 
- Vector search REST APIs 
- Knowledge graph modeling 
- CI/CD familiarity 
- Basic observability/logging

### Off-Limits Tech

Candidates should avoid:

- overly complex infrastructure
- unnecessary microservices
- over-engineering
- closed-source “magic” abstractions with no explanation
- copy-pasted AI-generated code without understanding
- fully no-code solutions

### What We Value

- clarity
- reasoning
- maintainability
- pragmatic tradeoffs
- strong engineering fundamentals
