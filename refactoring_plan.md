
## **Prompt for Centralized Logging, Configuration Enforcement, and Full Runtime Debugging in MQI System**

You are an expert Python systems architect, refactoring specialist, and debugger.
You will be given two reference documents:

* **`code_structure.md`** – complete project architecture, directory layout, and execution flow.
* **`module_structure.md`** – detailed module entry points and dependency contracts.

The MQI Interface System is a **distributed, microservice-based Python application** that coordinates multiple independent processes via RabbitMQ and manages state in SQLite.
Its architectural goals are:

1. **Centralized Logging** via `src.common.logger.get_logger` with uniform formatting and routing.
2. **Centralized Configuration** via `src.common.config_loader.load_config` loading a single YAML config (e.g., `config/config.development.yaml`), passed to all components at startup.
3. **Systematic Debugging** of runtime and design issues using a structured, multi-stage analysis pipeline.

---

### **Current Problem**

* Many modules still use **local logging** (e.g., `import logging` + `logging.getLogger(__name__)`) instead of the centralized logger.
* Some modules load configurations independently (e.g., direct YAML read or hardcoded settings) instead of using the shared `load_config` output from the orchestrator.
* Centralized logging/config was partially introduced, but **code drift** has led to inconsistencies, especially in worker modules and dashboard services.
* Known runtime issues include:

  * **Dashboard worker & GPU status not updating** during execution.
  * **Case scanner** detecting a new case but not triggering downstream workflow steps.
  * Potential downstream workflow errors after initial execution.

Likely causes include incorrect imports, unimplemented modules, message queue routing mismatches, database schema inconsistencies, and typos in process/module names.

---

### **Your Tasks**

#### **1. Audit Logging Across All Components**

* Locate every instance of local logger creation or setup outside `src.common.logger`.
* Identify modules that fail to initialize the central logger or create multiple loggers per process.

#### **2. Audit Configuration Loading**

* Locate all direct YAML/JSON reads, inline configs, or environment-only configs bypassing `load_config`.
* Identify modules reloading configs independently instead of receiving from the orchestrator.

#### **3. Static & Dynamic Debug Analysis**

Follow a **7-stage pipeline**:

1. **Project Inventory** – Build a complete import/module tree, compare with `PROCESS_MODULES`, find missing `__init__.py` and import inconsistencies.
2. **Static Analysis** – Detect undefined imports, wrong function names, message queue contract mismatches, and DB schema issues.
3. **Dynamic Analysis** – Step through orchestrator and worker execution, identify initialization sequence failures, trace workflow stalls.
4. **Root Cause Analysis** – For each issue, record file/line, log, likely cause, severity, and impact.
5. **Fix Proposal** – Provide diff patches with explanations; correct imports, align schemas, repair initialization sequences.
6. **Test & Verification Plan** – Create unit/integration tests ensuring dashboard updates and workflow continuity.
7. **Risk & Release Notes** – List breaking changes, migration steps, and rollback instructions.

#### **4. Refactor for Centralized Logging**

* Remove local loggers, replace with `get_logger`.
* Ensure logger initialization happens in each process’s `main.py`.
* Standardize log formats and levels system-wide.

#### **5. Refactor for Centralized Configuration**

* Remove direct config reads; load once in orchestrator and pass down.
* Ensure `PROCESS_MODULES` receive the orchestrator’s config path/object.

#### **6. Preserve Core Contracts**

* Keep public APIs, `PROCESS_MODULES` mappings, and entry point signatures unless fixing critical inconsistencies.
* Avoid altering MQ routing keys, DB schema, or business logic unless required for centralization/debugging compliance.

---

### **Output Requirements**

1. **Issue Table** – File, Current Behavior, Problem, Root Cause, Recommended Fix, Impact.
2. **Unified Diff Patches** – Minimal necessary changes grouped per file.
3. **Contract Tables** – MQ and DB schema expected vs actual.
4. **Execution Guide** – Commands, expected logs for verifying fixes.
5. **Before/After Examples** – Logging/config handling before vs after.
6. **Developer Notes** – How to correctly use central logging/config and debug pipelines.

