# TOGAF Documentation Mermaid Templates

Use these as starter templates for regulated enterprise documentation packs.
Replace placeholder labels (for example, `[System A]`, `[Owner]`, `[PII]`) with client-specific values.

## 1. Business Architecture Views

### 1.1 People View

```mermaid
---
title: Business Architecture - People View
---
flowchart LR
	Sponsor[Executive Sponsor]
	Owner[Business Process Owner]
	Steward[Data Steward]
	Architect[Solution Architect]
	Security[Security and Compliance]
	Ops[Operations Support]
	EndUser[End User Group]

	Sponsor -->|Strategic direction| Owner
	Owner -->|Requirements and policy| Architect
	Architect -->|Design constraints| Security
	Architect -->|Runbook requirements| Ops
	Steward -->|Data quality rules| Architect
	EndUser -->|Usability feedback| Owner
	Ops -->|Production metrics| Owner
```

### 1.2 Process View

```mermaid
---
title: Business Architecture - Process View
---
flowchart LR
	Start([Trigger Event]) --> Intake[Request Intake]
	Intake --> Validate{Policy Validation?}
	Validate -->|No| Reject[Reject and Notify]
	Validate -->|Yes| Assess[Risk and Impact Assessment]
	Assess --> Approve{Approval Required?}
	Approve -->|No| Execute[Execute Process]
	Approve -->|Yes| CAB[Governance Approval]
	CAB --> Execute
	Execute --> Verify[Outcome Verification]
	Verify --> Close[Close and Archive Evidence]
```

### 1.3 Functions View

```mermaid
---
title: Business Architecture - Functions View
---
flowchart TB
	Capability[Business Capability]

	subgraph CoreFunctions[Core Functions]
		F1[Identity and Access]
		F2[Case and Workflow Management]
		F3[Reporting and Compliance]
	end

	subgraph SupportingFunctions[Supporting Functions]
		S1[Data Governance]
		S2[Audit and Assurance]
		S3[Service Management]
	end

	Capability --> F1
	Capability --> F2
	Capability --> F3
	F1 --> S2
	F2 --> S1
	F3 --> S3
```

### 1.4 Information and Information Flows View

```mermaid
---
title: Business Architecture - Information and Information Flows View
---
sequenceDiagram
	participant User as Business User
	participant FE as Frontend
	participant BFF as Django BFF API
	participant AD as Active Directory
	participant DB as SQL Server
	participant Audit as Audit Repository

	User->>FE: Submit business request
	FE->>BFF: Send request payload
	BFF->>AD: Resolve identity and groups
	AD-->>BFF: Group membership
	BFF->>DB: Read and write business data
	DB-->>BFF: Result set
	BFF->>Audit: Write audit event
	BFF-->>FE: Response and status
	FE-->>User: Render outcome
```

### 1.5 Usability View

```mermaid
---
title: Business Architecture - Usability View
---
flowchart LR
	Persona[Persona and Accessibility Needs] --> Journey[Task Journey Mapping]
	Journey --> Prototype[Prototype and UX Review]
	Prototype --> UAT[User Acceptance Testing]
	UAT --> Decision{Meets Usability KPIs?}
	Decision -->|No| Iterate[Iterate Design]
	Iterate --> Prototype
	Decision -->|Yes| Release[Release to Production]
	Release --> Observe[Observe Support Tickets and CSAT]
	Observe --> Backlog[Feed Improvements to Backlog]
```

### 1.6 Performance View

```mermaid
---
title: Business Architecture - Performance View
---
flowchart TB
	Objectives[Business Performance Objectives]
	SLAs[Service Level Targets]
	KPIs[Operational KPIs]
	Telemetry[Monitoring and Telemetry]
	Review[Monthly Performance Review]
	Actions[Corrective and Preventive Actions]

	Objectives --> SLAs
	SLAs --> KPIs
	KPIs --> Telemetry
	Telemetry --> Review
	Review --> Actions
	Actions --> Objectives
```

## 2. Data Architecture Views

### 2.1 Data Entity View

```mermaid
---
title: Data Architecture - Data Entity View
---
erDiagram
	USER ||--o{ USER_ROLE : has
	ROLE ||--o{ USER_ROLE : maps
	AD_GROUP ||--o{ ROLE : grants
	USER ||--o{ SESSION : owns
	USER ||--o{ AUDIT_EVENT : triggers
	DOMAIN_RECORD ||--o{ AUDIT_EVENT : changes

	USER {
		string user_id
		string username
		string display_name
		datetime created_at
	}

	ROLE {
		string role_id
		string role_name
	}

	AD_GROUP {
		string group_dn
		string group_name
	}

	USER_ROLE {
		string user_id
		string role_id
	}

	SESSION {
		string session_id
		string user_id
		datetime expires_at
	}

	DOMAIN_RECORD {
		string record_id
		string business_key
		string status
	}

	AUDIT_EVENT {
		string event_id
		string actor_id
		string action
		datetime event_time
	}
```

### 2.2 Data Security View

```mermaid
---
title: Data Architecture - Data Security View
---
flowchart LR
	Classify[Data Classification]
	Collect[Data Collection]
	Encrypt[Encryption at Rest and in Transit]
	Access[Role-based Access Control]
	Mask[Masking and Tokenization]
	Retain[Retention and Legal Hold]
	Dispose[Secure Disposal]
	Audit[Security Audit Trail]

	Classify --> Collect
	Collect --> Encrypt
	Encrypt --> Access
	Access --> Mask
	Mask --> Retain
	Retain --> Dispose
	Access --> Audit
	Mask --> Audit
	Dispose --> Audit
```

### 2.3 Data Flow View

```mermaid
---
title: Data Architecture - Data Flow View
---
flowchart LR
	Source1[Corporate Source System]
	Source2[Enterprise API]
	Ingest[Adapter Layer Ingestion]
	Validate[Validation and Normalization]
	Persist[SQL Server Persistence]
	Cache[Application Cache]
	Consume[Reporting and UI Consumption]

	Source1 --> Ingest
	Source2 --> Ingest
	Ingest --> Validate
	Validate --> Persist
	Persist --> Cache
	Persist --> Consume
	Cache --> Consume
```

### 2.4 Logical Data Management View

```mermaid
---
title: Data Architecture - Logical Data Management View
---
flowchart TB
	Governance[Data Governance]
	Model[Logical Data Model]
	Quality[Data Quality Rules]
	Master[Master and Reference Data]
	Metadata[Metadata and Lineage]
	Lifecycle[Lifecycle and Archival]
	Recovery[Backup and Recovery]

	Governance --> Model
	Model --> Quality
	Model --> Master
	Model --> Metadata
	Quality --> Lifecycle
	Master --> Lifecycle
	Metadata --> Lifecycle
	Lifecycle --> Recovery
```

## 3. Applications Architecture Views

### 3.1 Logical Applications View

```mermaid
---
title: Applications Architecture - Logical Applications View
---
flowchart LR
	FE[React and TypeScript Frontend]
	API[Django BFF API Layer]
	SVC[Service Layer]
	ADP[Adapter Layer]
	DATA[MSSQL and Enterprise Data Sources]

	FE --> API
	API --> SVC
	SVC --> ADP
	SVC --> DATA
	ADP --> DATA
```

### 3.2 Physical Applications View

```mermaid
---
title: Applications Architecture - Physical Applications View
---
flowchart TB
	User[Corporate Browser Client]

	subgraph Edge[DMZ or Edge Tier]
		IIS[IIS with HttpPlatformHandler]
	end

	subgraph AppTier[Application Tier]
		U1[Uvicorn Worker 1]
		U2[Uvicorn Worker 2]
		U3[Uvicorn Worker N]
	end

	subgraph DataTier[Data Tier]
		SQL[MSSQL Primary]
		Replica[MSSQL Read Replica]
	end

	User --> IIS
	IIS --> U1
	IIS --> U2
	IIS --> U3
	U1 --> SQL
	U2 --> SQL
	U3 --> SQL
	SQL --> Replica
```

### 3.3 Integration and Interface View - BPE

```mermaid
---
title: Applications Architecture - Integration and Interface View (BPE)
---
sequenceDiagram
	participant BP as Business Process Engine
	participant API as Django BFF
	participant ERP as ERP Adapter
	participant CRM as CRM Adapter
	participant Notify as Notification Service

	BP->>API: Start orchestrated process
	API->>ERP: Request enterprise data
	ERP-->>API: Data response
	API->>CRM: Update customer state
	CRM-->>API: Update result
	API->>Notify: Send business notification
	Notify-->>BP: Process completion event
```

### 3.4 Integration and Interface View - ETL

```mermaid
---
title: Applications Architecture - Integration and Interface View (ETL)
---
flowchart LR
	SRC1[Source Database]
	SRC2[Source API]
	Extract[Extract Jobs]
	Transform[Transform and Data Quality]
	Stage[Staging Store]
	Load[Load Pipeline]
	DW[Enterprise Data Warehouse]

	SRC1 --> Extract
	SRC2 --> Extract
	Extract --> Transform
	Transform --> Stage
	Stage --> Load
	Load --> DW
```

### 3.5 Integration and Interface View - EAI

```mermaid
---
title: Applications Architecture - Integration and Interface View (EAI)
---
flowchart LR
	App1[Line of Business App A]
	App2[Line of Business App B]
	App3[Line of Business App C]
	Bus[Enterprise Integration Bus]
	Canonical[Canonical Message Model]
	Rules[Routing and Transformation Rules]

	App1 <--> Bus
	App2 <--> Bus
	App3 <--> Bus
	Bus --> Canonical
	Bus --> Rules
```

### 3.6 Authorisation and Authentication View

```mermaid
---
title: Applications Architecture - Authorisation and Authentication View
---
sequenceDiagram
	actor User as Corporate User
	participant FE as React Frontend
	participant IIS as IIS Windows Authentication
	participant API as Django on Uvicorn
	participant AD as Active Directory LDAP

	User->>FE: Open application
	FE->>IIS: HTTPS request
	IIS->>IIS: Authenticate with Kerberos or NTLM
	IIS->>API: Forward with WindowsAuthToken header
	API->>AD: LDAP group membership query
	AD-->>API: Group membership result
	API-->>FE: Authorised response with roles
	FE-->>User: Render permitted features
```

### 3.7 Applications Monitoring View

```mermaid
---
title: Applications Architecture - Applications Monitoring View
---
flowchart LR
	App[Application Components]
	Logs[Structured Logs]
	Metrics[Metrics and SLO Signals]
	Traces[Distributed Traces]
	SIEM[SIEM or Observability Platform]
	Alert[Alerting and On-call]
	ITSM[Incident and Problem Records]

	App --> Logs
	App --> Metrics
	App --> Traces
	Logs --> SIEM
	Metrics --> SIEM
	Traces --> SIEM
	SIEM --> Alert
	Alert --> ITSM
```

## 4. Technology Architecture Views

### 4.1 Network Topology View

```mermaid
---
title: Technology Architecture - Network Topology View
---
flowchart TB
	Internet[Corporate and External Networks]
	FW[Perimeter Firewall]
	DMZ[DMZ Segment]
	AppNet[Application Network Segment]
	DataNet[Data Network Segment]
	MgmtNet[Management Network Segment]

	Internet --> FW
	FW --> DMZ
	DMZ --> AppNet
	AppNet --> DataNet
	AppNet --> MgmtNet
```

### 4.2 Internet Facing Servers View

```mermaid
---
title: Technology Architecture - Internet Facing Servers View
---
flowchart LR
	Users[Approved User Populations]
	WAF[Web Application Firewall]
	LB[Load Balancer]
	IIS1[IIS Node 1]
	IIS2[IIS Node 2]
	App[Uvicorn App Pool]

	Users --> WAF
	WAF --> LB
	LB --> IIS1
	LB --> IIS2
	IIS1 --> App
	IIS2 --> App
```

### 4.3 Traffic Volumes and Bandwidth View

```mermaid
---
title: Technology Architecture - Traffic Volumes and Bandwidth View
---
flowchart LR
	Clients[Client Traffic]
	Edge[Edge Tier]
	App[Application Tier]
	Data[Data Tier]

	Clients -->|Peak: X_Mbps\nAvg: Y_Mbps| Edge
	Edge -->|Peak: A_RPS\nAvg Payload: B_KB| App
	App -->|Read: C_MBps\nWrite: D_MBps| Data
	App -->|External API: E_calls_per_min| Clients
```

## 5. Client, Server and Storage View

```mermaid
---
title: Client, Server and Storage View
---
flowchart LR
	subgraph Clients[Client Tier]
		Browser[Managed Browser]
		Mobile[Managed Mobile Device]
	end

	subgraph Servers[Server Tier]
		IIS[IIS and HttpPlatformHandler]
		Uvicorn[Django and Uvicorn]
		Worker[Background Worker]
	end

	subgraph Storage[Storage Tier]
		SQL[MSSQL Database]
		Blob[Document and Object Storage]
		Backup[Backup Vault]
	end

	Browser --> IIS
	Mobile --> IIS
	IIS --> Uvicorn
	Uvicorn --> Worker
	Uvicorn --> SQL
	Uvicorn --> Blob
	SQL --> Backup
	Blob --> Backup
```

## 6. Systems Management View

```mermaid
---
title: Systems Management View
---
flowchart TB
	Monitor[Monitoring and Event Management]
	Incident[Incident Management]
	Problem[Problem Management]
	Change[Change and Release Management]
	Config[Configuration Management Database]
	Patch[Patch and Vulnerability Management]
	Continuity[Backup, Restore, and DR Testing]
	Compliance[Compliance Reporting and Evidence]

	Monitor --> Incident
	Incident --> Problem
	Problem --> Change
	Change --> Config
	Config --> Patch
	Patch --> Monitor
	Change --> Continuity
	Continuity --> Compliance
	Compliance --> Change
```
