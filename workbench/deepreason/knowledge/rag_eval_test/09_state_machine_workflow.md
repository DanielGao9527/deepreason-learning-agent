# RAG Eval: State Machine Workflow

Document id: rag_eval_state_machine_workflow.

The default reasoning workflow follows intake, plan, retrieve, reason, evidence_audit, gate, act_or_answer, verify, consolidate, and respond. Retry edges can return from evidence_audit or gate back to retrieve when evidence is insufficient.

