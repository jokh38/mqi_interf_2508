# MQI Communicator 시스템 사용 가이드

## 개요

MQI Communicator는 의료 물리 QA(Quality Assurance) 워크플로우를 자동화하기 위해 설계된 시스템입니다. 새로운 데이터(Case)를 감지하고, 관련 파일을 전송하며, 원격 서버에서 계산을 실행하고, 전체 프로세스를 관리하는 역할을 합니다.

## 아키텍처

이 시스템은 여러 독립적인 컴포넌트가 메시지 큐를 통해 통신하는 마이크로서비스 아키텍처를 기반으로 합니다.

-   **Main Orchestrator (`main_orchestrator.py`):** 전체 시스템을 시작하고, 모니터링하며, 관리하는 최상위 컨트롤러입니다.
-   **Conductor (`src/conductor`):** 전체 워크플로우의 상태를 관리하고, 각 단계의 진행을 조율합니다.
-   **Dashboard (`src/dashboard`):** 시스템의 상태를 시각적으로 보여주는 웹 대시보드입니다.
-   **Workers (`src/workers`):** 개별 작업을 수행하는 컴포넌트들입니다.
    -   **Case Scanner:** 새로운 Case가 있는지 주기적으로 확인합니다.
    -   **File Transfer:** 원격 서버로 파일을 전송(SFTP)합니다.
    -   **Remote Executor:** 원격 서버에서 명령(SSH)을 실행합니다.
    -   **System Curator:** 시스템의 상태(예: GPU 사용량)를 모니터링합니다.
    -   **Archiver:** 오래된 데이터를 백업하고 정리합니다.
-   **Message Queue (RabbitMQ):** 컴포넌트 간의 비동기 통신을 담당합니다.

## 설정 관리

### 중앙집중식 설정 시스템

시스템의 모든 설정은 중앙집중식 방식으로 관리됩니다:

-   **설정 로딩**: `MainOrchestrator`가 시작 시 `src/common/config_loader.py`를 사용하여 설정 파일을 **한 번만** 로드합니다.
-   **설정 배포**: 설정 객체는 `ProcessManager`를 통해 JSON으로 직렬화되어 자식 프로세스들에게 전달됩니다.
-   **환경 변수**: `MQI_CONFIG_PATH` 환경 변수가 우선시되며, 설정되지 않은 경우에만 기본 경로를 사용합니다.
-   **통합 검증**: 모든 필요한 설정 섹션(DB, RabbitMQ, SFTP, SSH)에 대한 통합 검증을 수행합니다.
-   **설정 마이그레이션**: 기존에 하드코딩되어 있던 모든 설정(큐 매핑, 원격 경로, 기본값 등)이 `config.yaml` 파일로 이관되었습니다.

### 주요 설정 항목

-   **`database`**: 시스템의 상태 및 로그를 저장하는 SQLite 데이터베이스 파일의 경로
-   **`rabbitmq`**: RabbitMQ 서버의 접속 URL과 모든 큐 매핑
-   **`processes`**: 각 워커 프로세스의 활성화 여부와 재시작 정책 (지수 백오프, 최대 재시작 제한)
-   **`scanner`**: Case Scanner의 스캔 디렉토리, 주기, 완료된 스캔의 데이터베이스 저장
-   **`sftp`**: File Transfer 워커의 SFTP 서버 접속 정보
-   **`ssh`**: Remote Executor 워커의 SSH 서버 접속 정보
-   **`workflows`**: 워크플로우 단계 정의와 상태 관리 (별도 `status`와 `current_step` 컬럼 사용)
-   **`remote_commands`**: 각 워크플로우 단계에서 실행될 원격 명령어

## 설치 및 실행

### 패키지 설치

```bash
# 필요한 의존성 설치
pip3 install -r requirements.txt
```

### 전체 시스템 실행

전체 시스템을 한 번에 시작하려면 `run.bat`을 실행하거나 다음 명령어를 사용합니다.

```bash
python run_file_transfer.py
```

이 명령은 `config.default.yaml` 파일에 활성화(`enabled: true`)된 모든 컴포넌트를 시작합니다.

### 개별 컴포넌트 실행

개발 또는 테스트 목적으로 각 컴포넌트를 개별적으로 실행할 수 있습니다:

```bash
# 환경 변수 설정
set MQI_CONFIG_PATH=config/config.default.yaml

# 개별 워커 실행
python -m src.workers.case_scanner.main
python -m src.workers.file_transfer.main
python -m src.workers.remote_executor.main
python -m src.workers.system_curator.main
python -m src.workers.archiver.main

# Conductor 실행
python -m src.conductor.main

# Dashboard 실행
python -m src.dashboard.main
```

## 워크플로우 예시 (`default_qa`)

1.  **Case 감지:** `Case Scanner`가 `scanner.target_directory`에서 새로운 Case 폴더를 감지합니다.
2.  **워크플로우 시작:** `Conductor`가 `new_case_found` 메시지를 받고, 해당 Case에 대한 새로운 워크플로우를 시작합니다.
3.  **자원 할당 및 명령어 생성:** `Conductor`가 가용한 GPU를 확인하고, 워크플로우의 첫 번째 단계(`run_interpreter`)에 대한 명령어를 생성합니다.
4.  **명령어 발행:** `Conductor`가 `execute_command` 메시지를 `remote_executor_queue`로 발행합니다.
5.  **원격 실행:** `Remote Executor`가 메시지를 받아 SSH를 통해 원격 서버에서 명령을 실행합니다.
6.  **결과 보고:** `Remote Executor`가 실행 결과를 `execution_succeeded` 또는 `execution_failed` 메시지로 `conductor_queue`에 보고합니다.
7.  **다음 단계 진행:** `Conductor`가 성공 메시지를 받고, 워크플로우의 다음 단계(`run_moqui_sim`)를 진행합니다.
8.  **워크플로우 완료:** 모든 단계가 성공적으로 완료되면, `Conductor`는 해당 Case의 상태를 `COMPLETED`로 변경합니다. 만약 중간에 실패하면 `FAILED`로 변경하고, 할당된 자원을 해제합니다.

## 주요 컴포넌트 상세 설명

### Main Orchestrator

-   `ProcessManager`를 사용하여 설정 파일에 정의된 모든 활성 프로세스를 시작하고 관리합니다.
-   `HealthMonitor`를 사용하여 시스템의 전반적인 상태와 각 프로세스의 동작을 모니터링합니다.
-   `SIGINT` (Ctrl+C) 또는 `SIGTERM` 신호를 받으면 모든 프로세스를 안전하게 종료하는 역할을 합니다.

### Conductor

-   `WorkflowManager`를 통해 워크플로우의 로직을 관리합니다.
-   `StateService`를 사용하여 데이터베이스에 각 Case의 현재 상태(예: `QUEUED`, `RUNNING_run_interpreter`, `COMPLETED`, `FAILED`)를 기록하고 조회합니다.
-   GPU와 같은 공유 자원을 관리하고, 필요한 시점에 Case에 할당하거나 해제합니다.

### Dashboard
-   `DashboardService`를 통해 시스템의 상태 정보를 수집하고 제공합니다.
-   `FastAPI`를 사용하여 웹 인터페이스를 제공합니다.
-   `Uvicorn`을 통해 비동기적으로 실행됩니다.

### Workers (이벤트 기반 아키텍처)

모든 워커가 일관된 이벤트 기반 모델을 따릅니다:

-   **`Case Scanner`**: 
    - **메시지 기반 처리**: 지정된 큐에서 메시지를 소비하여 스캔 작업 수행
    - **영속적 상태 저장**: 완료된 스캔을 SQLite 데이터베이스에 저장하여 재시작 시에도 중복 처리 방지
    - **데이터 무결성**: 처리 성공 후 데이터베이스에 새 항목 기록

-   **`File Transfer`**: 
    - **SFTP 서비스**: `sftp_service.py`를 통한 원격 파일 전송
    - **향상된 에러 핸들링**: 안전한 리소스 관리와 타입 검증

-   **`Remote Executor`**: 
    - **SSH 서비스**: 원격 명령 실행과 결과 보고
    - **버그 수정**: `self.messaging` 오타 수정, `correlation_id` 접근성 개선

-   **`System Curator`**: 
    - **이벤트 기반 전환**: 기존 폴링 메커니즘에서 메시지 기반 처리로 변경
    - **`system_curator_queue`에서 메시지 소비**: 시스템 자원 모니터링 요청 처리

-   **`Archiver`**: 
    - **이벤트 기반 전환**: APScheduler 기반에서 메시지 기반 아키텍처로 변경
    - **`archiver_queue`에서 메시지 소비**: 아카이브 작업 요청 처리
    - **주기적 작업**: 스케줄러 서비스 또는 Conductor가 적절한 시점에 메시지 전송

**공통 개선사항:**
- **중앙집중식 로깅**: 모든 모듈이 `src.common.logger.get_logger` 사용
- **스레드 안전성**: `extra` 매개변수를 통한 동적 로깅 정보 전달
- **리소스 관리**: 안전한 초기화 및 정리 패턴 적용