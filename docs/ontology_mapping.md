# Ontology mapping — injuries → SNOMED CT → contraindicated exercises

This table documents the **curated** clinical ontology seeded by
`app/ingestion/ontology.py` (`load_ontology`). Each injury the platform reasons about is
mapped to a SNOMED CT concept and to the exercises that are contraindicated for it.

> **Curated subset, not the full release.** The SNOMED CT codes below are a small, hand-picked
> subset covering common musculoskeletal conditions relevant to strength coaching. They are
> **not** the complete SNOMED CT terminology. This file (together with the `SNOMED_CONCEPTS`
> list in `app/ingestion/ontology.py`) is the documented **extension point**: to support the
> full terminology later, load the official SNOMED CT release into `:SnomedConcept` nodes
> keyed on `code` and extend the `:Injury)-[:MAPS_TO]->(:SnomedConcept` mappings. No schema
> change is required.

## Injury → SNOMED concept → contraindicated exercises

| Injury (id) | SNOMED CT concept | SNOMED code | Body region | Contraindicated exercises | Rationale |
|---|---|---|---|---|---|
| Rotator cuff injury (`rotator_cuff_tear`) | Rotator cuff syndrome | 202856007 | Shoulder | Barbell overhead press, Barbell bench press | Overhead / heavy horizontal pressing loads the cuff at vulnerable ranges. |
| Lateral epicondylitis (`tennis_elbow`) | Lateral epicondylitis | 202855006 | Elbow | Barbell biceps curl | Loaded elbow flexion strains the common extensor origin. |
| ACL rupture (`acl_tear`) | Rupture of anterior cruciate ligament | 239720000 | Knee | Machine leg extension | Open-chain knee extension drives anterior tibial translation. |
| Lumbar strain (`lumbar_strain`) | Sprain of lumbar spine | 209583007 | Lumbar spine | Conventional deadlift, Barbell back squat | Heavy hip-hinge / axial loading aggravates a strained lumbar spine. |
| Patellar tendinopathy (`patellar_tendinopathy`) | Patellar tendinopathy | 202580003 | Knee | Barbell back squat | Deep loaded knee flexion increases patellar tendon load. |

## Graph shape

The loader creates these relationship types (all idempotent via `MERGE`):

- `(:Exercise)-[:TARGETS]->(:MuscleGroup)`
- `(:Exercise)-[:REQUIRES]->(:Equipment)`
- `(:Exercise)-[:CONTRAINDICATED_FOR]->(:Injury)`
- `(:Injury)-[:MAPS_TO]->(:SnomedConcept)`
- `(:SnomedConcept)-[:AFFECTS]->(:BodyRegion)`
- `(:MuscleGroup)-[:IN_REGION]->(:BodyRegion)`
