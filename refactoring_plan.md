
## **Prompt for AI Codebase Diagnosis & Repair**

You are an expert Python software architect and debugger.
You will receive the following materials:

1. **Full project structure** from `code_structure.md` and `module_structure.md`.
2. Known runtime issues and logs.
3. Configuration files and dependency list (provided).
4. The goal: **systematically detect and fix all runtime and design errors** in a multi-module distributed Python system.

---

### **System Context**

* The codebase is a **distributed orchestrator/worker/dashboard system** built in Python.
* Components:

  * **Orchestrator (`src/main_orchestrator.py`)**: Central entry point, launches multiple processes through `ProcessManager`.
  * **Workers**: `case_scanner`, `file_transfer`, `remote_executor`, `system_curator`, `archiver`.
  * **Dashboard**: Displays worker & GPU status, job progress.
  * **Conductor**: Coordinates workflow execution.
  * **Shared Utilities**: Database manager, messaging (RabbitMQ), config loader, workflow manager, etc.
* Entry command example:

  ```bash
  python3 -m src.main_orchestrator config/config.development.yaml
  ```
* `PROCESS_MODULES` maps process names to module paths (e.g., `"conductor": "src.conductor.main"`, `"dashboard": "src.dashboard.main"`, etc.).

---

### **Known Runtime Issues**

1. **Dashboard worker & GPU status do not update** during execution.
2. **Case scanner** detects a new case but **no further workflow steps are executed** afterward.
3. **Only initial execution** was tested — there may be additional errors later in the workflow once execution proceeds.
4. Suspected root causes include:

   * Incorrect `import` paths or wrong function/method names between components.
   * Calls to modules that are unimplemented or not properly initialized.
   * Message queue routing key or payload schema mismatches.
   * Database schema mismatches or transaction issues.
   * Typos in process/module names (e.g., `dashboard_seryamlvice`).

---

### **Your Tasks**

Follow this **7-stage analysis pipeline**:

1. **Project Inventory**

   * Build a complete import/module tree from provided files.
   * Compare actual file locations vs `PROCESS_MODULES` mapping.
   * Identify missing `__init__.py` files, absolute/relative import inconsistencies.

2. **Static Analysis**

   * Find **undefined imports**, wrong method/function names, and modules referenced but not implemented.
   * Detect typos in process/module names.
   * Extract **message queue contracts** (exchange, queue, routing key, payload schema) and verify that sender/receiver match.
   * Extract **database access patterns** and check for schema mismatches.

3. **Dynamic Analysis**

   * Simulate or step through full orchestrator execution and individual worker runs.
   * Identify initialization sequence issues (e.g., database, message queue, config loader not ready before use).
   * Trace execution after case scanner detection to see where workflow stalls.

4. **Root Cause Analysis**

   * For each issue, document:

     * **File & line**
     * **Observed behavior/log**
     * **Likely cause**
     * **Severity & impact**

5. **Fix Proposal**

   * Suggest **code changes as diff patches** with explanations.
   * For unimplemented modules, create temporary stubs with TODO markers.
   * Correct import paths, fix function names, align message/database schemas, and repair initialization sequences.

6. **Test & Verification Plan**

   * Propose unit & integration test cases for each fix.
   * Ensure that:

     * Dashboard worker/GPU status updates in real time.
     * Case scanner detection triggers downstream workflow modules.
     * All integration tests (e.g., `test_complete_workflow.py`, `test_failure_recovery.py`) pass.

7. **Risk & Release Notes**

   * List breaking changes and migration steps.
   * Provide rollback instructions.

---

### **Output Format**

1. **Issue Table** (Type, File\:Line, Log/Error, Root Cause, Fix Summary, Impact)
2. **Diff patches** grouped by file with explanations.
3. **Contract tables** for message queue & database schema (expected vs actual).
4. **Execution guide** for verifying fixes (commands, expected logs).
5. **Updated test plan**.

---

**Important Notes**

* You must cover **both current known issues** and **potential downstream issues** that will appear after fixing the first errors.
* Always validate that component contracts (imports, message formats, DB schemas) match across all producers & consumers.
* Prioritize changes that unblock execution before addressing optimization or refactoring.


