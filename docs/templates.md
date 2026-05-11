# Mermaid Diagram Templates

## 1. Business Architecture Views

### 1.1 People View

```mermaid
---
title: Business Architecture - People View
---
flowchart LR
	subgraph Roles[User Roles]
		Admin[Role: Application Admin]
		Approver[Role: Business Approver]
		Uploader[Role: Data Uploader]
		Viewer[Role: Compliance Viewer]
		Auditor[Role: External Auditor]
	end

	subgraph Capabilities[System Capabilities and Components]
		CapApprove[Approval Workbench]
		CapUpload[Bulk Upload and Validation]
		CapCase[Case Search and Case Detail]
		CapReport[Regulatory Reporting]
		CapConfig[Role and Policy Administration]
		CapAudit[Audit Evidence Export]
	end

	Admin -->|configure and govern| CapConfig
	Admin -->|override and approve| CapApprove
	Approver -->|approve or reject| CapApprove
	Uploader -->|submit and correct| CapUpload
	Uploader -->|track submissions| CapCase
	Viewer -->|read only| CapCase
	Viewer -->|read only| CapReport
	Auditor -->|evidence access| CapAudit
	CapUpload -->|creates work items for| CapApprove
	CapApprove -->|publishes outcomes to| CapReport
```

### 1.2 Process View

```mermaid
---
title: Business Architecture - Process View (BPMN-Style)
---
flowchart LR
	subgraph LaneA[Pool: Requesting Team]
		Start(((Start Event)))
		Submit[User Task: Submit Request]
		Evidence[Manual Task: Provide Supporting Evidence]
	end

	subgraph LaneB[Pool: Solution Workflow]
		Validate[Service Task: Validate Request]
		Policy{Gateway: Policy Passed?}
		Route[Service Task: Route for Approval]
		AutoRun[Service Task: Automated Processing]
		Notify[Service Task: Notify Outcome]
	end

	subgraph LaneC[Pool: Approver Function]
		Approve[User Task: Approve or Reject]
	end

	subgraph LaneD[Pool: External Processes]
		ITSM[Manual or Semi-Automated ITSM Activity]
		EnterpriseAPI[Automated Enterprise API Update]
		End(((End Event)))
	end

	Start --> Submit --> Validate --> Policy
	Policy -->|No| ITSM
	ITSM -. handoff .-> Evidence
	Evidence --> Validate
	Policy -->|Yes| Route --> Approve
	Approve -->|Rejected| ITSM
	Approve -->|Approved| AutoRun --> EnterpriseAPI --> Notify --> End
```

### 1.3 Functions View

```mermaid
---
title: Business Architecture - Functions View (Use Case Template)
---
flowchart LR
	subgraph Actors[Actors]
		A1[Admin]
		A2[Approver]
		A3[Uploader]
		A4[Viewer]
	end

	subgraph UseCases[Solution Use Cases]
		U1([Manage Roles and Policy Rules])
		U2([Upload and Validate Submission])
		U3([Approve or Reject Submission])
		U4([View Case and Status])
		U5([Generate Compliance Report])
		U6([Export Audit Evidence])
	end

	A1 --> U1
	A1 --> U3
	A2 --> U3
	A3 --> U2
	A3 --> U4
	A4 --> U4
	A4 --> U5
	A4 --> U6
	U2 -->|uses| U4
	U3 -->|updates| U4
	U5 -->|sources evidence from| U6
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
flowchart TB
	subgraph Contexts[Operational Contexts]
		Office[Office Environment]
		Shop[Shop Floor Environment]
		Field[On-wing Maintenance Environment]
		Remote[Remote and Low-bandwidth Environment]
	end

	subgraph Constraints[Usability Constraints]
		Noise[High noise and PPE use]
		Light[Variable lighting and weather]
		Network[Intermittent connectivity]
		TimeCritical[Time-critical tasks]
		Accessibility[Accessibility and keyboard-only needs]
	end

	subgraph DesignResponses[UX and UI Responses]
		Responsive[Responsive layouts by device class]
		Touch[Large touch targets and reduced precision demand]
		Contrast[High contrast and readable typography]
		Offline[Offline-safe draft and retry workflows]
		RoleUX[Role-based quick actions and simplified navigation]
	end

	subgraph Validation[Validation and Evidence]
		Scenario[Scenario-based usability testing]
		UAT[Context-specific UAT in each environment]
		Training[Role-focused SOPs and training packs]
		KPI[Task time, error rate, and satisfaction metrics]
	end

	Office --> Accessibility
	Shop --> Noise
	Field --> Light
	Field --> TimeCritical
	Remote --> Network
	Noise --> Touch
	Light --> Contrast
	Network --> Offline
	TimeCritical --> RoleUX
	Accessibility --> Responsive
	Responsive --> Scenario
	Touch --> UAT
	Contrast --> UAT
	Offline --> UAT
	RoleUX --> Training
	Scenario --> KPI
	UAT --> KPI
```

### 1.6 Performance View

```mermaid
---
title: Business Architecture - Performance View
---
flowchart TB
	subgraph NFRs[Key Performance Needs]
		Latency[Latency: P95 and P99 API targets]
		Throughput[Throughput: peak requests per second]
		Availability[Availability target and allowed downtime]
		Concurrency[Concurrent user capacity]
		DataPerf[Database read and write response targets]
		Recovery[RTO and RPO objectives]
	end

	subgraph Controls[Engineering and Operational Controls]
		Caching[Cache strategy and invalidation rules]
		Scale[Horizontal scale plan for Uvicorn workers]
		DBTune[MSSQL indexing and query tuning]
		Queue[Async processing for long-running tasks]
		Observe[Telemetry, SLO dashboards, and alerts]
		LoadTest[Load, stress, and soak test regimes]
	end

	subgraph Governance[Assurance and Governance]
		Baseline[Performance baseline per release]
		Gate[Release gate on NFR pass criteria]
		Review[Capacity and performance review cadence]
	end

	Latency --> Caching
	Throughput --> Scale
	Availability --> Observe
	Concurrency --> Scale
	DataPerf --> DBTune
	Recovery --> Queue
	Caching --> Baseline
	Scale --> Baseline
	DBTune --> Gate
	Queue --> Gate
	Observe --> Review
	LoadTest --> Gate
	Baseline --> Review
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
	subgraph IdentityAccess[Identity and Access Control]
		User[Business User]
		IIS[IIS Windows Authentication]
		LDAP[Active Directory and LDAP Groups]
		RoleMap[Application Role Mapping]
		Policy[Row, Record, or Domain Access Policy]
	end

	subgraph DataDomains[Protected Data Domains]
		PII[Personal and Sensitive Data]
		Ops[Operational Data]
		Ref[Reference Data]
		Audit[Audit and Evidence Data]
	end

	subgraph DataControls[Data Protection Controls]
		Mask[Masking and redaction]
		Encrypt[Encryption at rest and in transit]
		Least[Least privilege access]
		Admin[Privileged access administration]
		Monitor[Access logging and monitoring]
	end

	User --> IIS --> LDAP --> RoleMap --> Policy
	Policy -->|permits or denies| PII
	Policy -->|permits or denies| Ops
	Policy -->|permits or denies| Ref
	Policy -->|permits or denies| Audit
	PII --> Mask
	Ops --> Encrypt
	Ref --> Least
	Audit --> Monitor
	Admin --> Policy
	Mask --> Monitor
	Encrypt --> Monitor
	Least --> Monitor
```

### 2.3 Data Flow View

```mermaid
---
title: Data Architecture - Data Flow View
---
flowchart LR
	subgraph SteadyState[Steady-state Interfaces]
		SrcDB[Source Database]
		SrcAPI[Enterprise API]
		SrcFile[Managed File Drop]
		Adapters[Adapter and Interface Layer]
		Validate[Validation, mapping, and reconciliation]
		TargetDB[MSSQL Operational Store]
		UI[Frontend and reporting consumers]
	end

	subgraph Migration[One-off Migration Flows]
		Legacy[Legacy source extract]
		Stage[Migration staging area]
		Cleanse[Data cleansing and transformation]
		Load[Migration load process]
		Cutover[Cutover validation and sign-off]
	end

	SrcDB -->|ODBC, JDBC, or replica feed| Adapters
	SrcAPI -->|REST, SOAP, or message interface| Adapters
	SrcFile -->|CSV, XLSX, or fixed-width file| Adapters
	Adapters --> Validate --> TargetDB --> UI
	Legacy --> Stage --> Cleanse --> Load --> TargetDB
	Load --> Cutover
	Cutover --> UI
```

### 2.4 Logical Data Management View

```mermaid
---
title: Data Architecture - Logical Data Management View
---
flowchart TB
	subgraph Administration[Administration and Security]
		Steward[Data stewardship]
		DBA[Database administration]
		SecAdmin[Security administration]
		Meta[Metadata and lineage management]
		Quality[Data quality management]
	end

	subgraph Lifecycle[Logical Data Lifecycle]
		Create[Create and ingest]
		Use[Use and maintain]
		Share[Share and publish]
		Retain[Retention control]
		Archive[Archive and retrieve]
		Delete[Secure deletion and disposal]
	end

	subgraph Safeguards[Lifecycle Safeguards]
		Classify[Classification and ownership]
		Access[Role-based access and approvals]
		Backup[Backup and recovery]
		Legal[Legal hold and retention exceptions]
		Audit[Administrative audit trail]
	end

	Steward --> Create
	DBA --> Use
	SecAdmin --> Access
	Meta --> Share
	Quality --> Use
	Create --> Use --> Share --> Retain --> Archive --> Delete
	Classify --> Create
	Access --> Use
	Backup --> Archive
	Legal --> Retain
	Audit --> Delete
	Access --> Audit
	Backup --> Audit
	Legal --> Audit
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
flowchart LR
	subgraph Access[Remote, Mobile, and Site Access]
		RemoteUser[Remote User Laptop]
		Mobile[Managed Mobile Device]
		OfficeLAN[Office User VLAN]
		ShopLAN[Shop Floor or OT VLAN]
		BranchLAN[Remote Site LAN]
	end

	subgraph WAN[WAN and Edge Connectivity]
		Internet[Internet]
		VPN[VPN Gateway or ZTNA Service]
		SDWAN[SD-WAN or MPLS Edge Router]
		FW[Perimeter Firewall and NAT]
	end

	subgraph Hosting[Solution Hosting Zones]
		DMZ[DMZ or Reverse Proxy Subnet]
		AppNet[Application Subnet - IIS and Uvicorn]
		DataNet[Data Subnet - MSSQL]
		MgmtNet[Management Subnet - Monitoring and Backup]
	end

	subgraph Enterprise[Enterprise Service Networks]
		AD[Active Directory and LDAP Services]
		API[Enterprise API or Database Services]
	end

	RemoteUser -->|TLS 1.2+ or IPsec VPN| VPN
	Mobile -->|TLS 1.2+ managed mobile access| VPN
	BranchLAN -->|Encrypted MPLS or SD-WAN overlay| SDWAN
	OfficeLAN -->|HTTPS 443| FW
	ShopLAN -->|HTTPS 443| FW
	Internet -->|HTTPS 443| FW
	VPN --> FW
	SDWAN --> FW
	FW -->|HTTPS 443| DMZ
	DMZ -->|HTTPS 443 reverse proxy| AppNet
	AppNet -->|TDS 1433 over TLS| DataNet
	AppNet -->|LDAPS 636| AD
	AppNet -->|HTTPS 443 or vendor protocol| API
	MgmtNet -->|Operations and backup traffic| AppNet
	MgmtNet -->|Database admin and backup traffic| DataNet
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
	subgraph Access[Remote, Mobile, and Site Access]
		RemoteUser[Remote User Laptop]
		Mobile[Managed Mobile Device]
		OfficeLAN[Office User VLAN]
		ShopLAN[Shop Floor or OT VLAN]
		BranchLAN[Remote Site LAN]
	end

	subgraph WAN[WAN and Edge Connectivity]
		VPN[VPN Gateway or ZTNA Service]
		SDWAN[SD-WAN or MPLS Edge Router]
		FW[Perimeter Firewall and NAT]
	end

	subgraph Hosting[Solution Hosting Zones]
		DMZ[DMZ or Reverse Proxy Subnet]
		AppNet[Application Subnet - IIS and Uvicorn]
		DataNet[Data Subnet - MSSQL]
	end

	subgraph Enterprise[Enterprise Service Networks]
		AD[Active Directory and LDAP Services]
		API[Enterprise API or Database Services]
	end

	RemoteUser -->|TLS VPN; Peak remote_peak_mbps; Spare remote_spare_mbps| VPN
	Mobile -->|Managed mobile access; Peak mobile_peak_mbps; Spare mobile_spare_mbps| VPN
	BranchLAN -->|SD-WAN or MPLS; Peak branch_peak_mbps; Spare branch_spare_mbps| SDWAN
	OfficeLAN -->|HTTPS 443; Peak office_peak_mbps; Spare office_spare_mbps| FW
	ShopLAN -->|HTTPS 443; Peak shop_peak_mbps; Spare shop_spare_mbps| FW
	VPN -->|Remote access aggregate; Peak vpn_peak_mbps; Spare vpn_spare_mbps| FW
	SDWAN -->|WAN aggregate; Peak wan_peak_mbps; Spare wan_spare_mbps| FW
	FW -->|North-south HTTPS 443; Peak edge_peak_mbps; Spare edge_spare_mbps| DMZ
	DMZ -->|Reverse proxy to app; Peak dmz_peak_mbps; Spare dmz_spare_mbps| AppNet
	AppNet -->|SQL TDS over TLS; Peak data_peak_MBps; Spare data_spare_MBps| DataNet
	AppNet -->|LDAPS 636; Peak ldap_peak_kbps; Spare ldap_spare_kbps| AD
	AppNet -->|HTTPS 443 or message traffic; Peak api_peak_mbps; Spare api_spare_mbps| API
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

### 6.1 Backup and Restore View

```mermaid
---
title: Systems Management View - Backup and Restore
---
flowchart LR
	subgraph ProtectedEstate[Protected Solution Estate]
		App[Application servers and middleware]
		DB[Databases]
		FileStore[File and object storage]
	end

	subgraph BackupPlatform[Backup and Recovery Mechanisms]
		Agent[Backup agents or snapshot integration]
		Policy[Backup policy and schedule]
		Vault[Primary backup repository]
		Offsite[Off-site or immutable copy]
		Catalog[Restore catalog and recovery runbooks]
		Test[Restore test and validation]
	end

	subgraph Governance[Recovery Governance]
		Ops[Operations and recovery team]
		ITSM[Incident, change, and recovery records]
		Targets[RTO and RPO targets]
	end

	App --> Agent
	DB --> Agent
	FileStore --> Agent
	Agent --> Policy --> Vault --> Offsite
	Vault --> Catalog
	Catalog --> Test
	Ops --> Catalog
	Targets --> Policy
	Targets --> Test
	Test --> ITSM
	Ops --> ITSM
```

### 6.2 Systems Archiving and Purging View

```mermaid
---
title: Systems Management View - Systems Archiving and Purging
---
flowchart LR
	subgraph Policy[Retention and Control Inputs]
		Classify[Data classification and ownership]
		Retention[Retention schedule and policy]
		Legal[Legal hold and exception handling]
		Approval[Business and records approval]
	end

	subgraph DataStores[Managed Data Stores]
		Operational[Operational data store]
		ArchiveStore[Archive storage tier]
		Purge[Approved purge and disposal job]
		Evidence[Archive and purge audit evidence]
	end

	subgraph Operations[Operational Controls]
		Select[Archiving and purge selection rules]
		Review[Archive and purge review]
		Hold[Legal hold prevents purge]
	end

	Classify --> Select
	Retention --> Select
	Operational --> Select
	Select -->|archive candidate set| ArchiveStore
	Select -->|purge candidate set| Review
	Approval --> Review
	Legal --> Hold
	Hold -. blocks .-> Review
	Review --> PurgeExec[Purge execution]
	PurgeExec --> Evidence
	ArchiveStore --> Evidence
```

### 6.3 Service, Application and Technology Monitoring and Alerting View

```mermaid
---
title: Systems Management View - Monitoring and Alerting
---
flowchart LR
	subgraph SignalSources[Service, Application, and Technology Signal Sources]
		Service[Service KPIs and user journeys]
		App[Application health and performance]
		DB[Database health and capacity]
		Infra[OS, VM, network, and storage telemetry]
		Synth[Synthetic probes]
	end

	subgraph Telemetry[Collection and Analysis]
		Metrics[Metrics collection]
		Logs[Central log platform]
		Traces[Tracing and APM]
		Rules[Thresholds, baselines, and anomaly rules]
	end

	subgraph Response[Response and Governance]
		Dash[Dashboards and service views]
		Alert[Alerts and escalation policies]
		Ops[Operations and on-call]
		ITSM[Incident, problem, and change records]
		Review[Capacity and service review]
	end

	Service --> Metrics
	App --> Metrics
	App --> Logs
	App --> Traces
	DB --> Metrics
	Infra --> Metrics
	Infra --> Logs
	Synth --> Rules
	Metrics --> Rules
	Logs --> Rules
	Traces --> Rules
	Metrics --> Dash
	Logs --> Dash
	Traces --> Dash
	Rules --> Alert --> Ops --> ITSM
	Dash --> Review
	ITSM --> Review
```

### 6.4 Systems Instrumentation View

```mermaid
---
title: Systems Management View - Systems Instrumentation
---
flowchart LR
	subgraph Components[Instrumented Components]
		Frontend[Frontend and user journey points]
		API[API and service layer]
		Adapter[Integration adapters]
		DB[Database tier]
		Host[OS, server, and platform layer]
	end

	subgraph Controls[Instrumentation Mechanisms]
		LogLib[Structured logging and audit hooks]
		MetricExp[Metric exporters]
		TraceCtx[Trace propagation and correlation IDs]
		Agent[Host agents and forwarders]
		Collector[Telemetry collector or gateway]
	end

	subgraph Consumers[Operational Consumers]
		Obs[Observability platform]
		SIEM[Security monitoring]
		Dash[Dashboards and reports]
	end

	Frontend --> MetricExp
	API --> LogLib
	API --> MetricExp
	API --> TraceCtx
	Adapter --> LogLib
	Adapter --> MetricExp
	Adapter --> TraceCtx
	DB --> Agent
	Host --> Agent
	LogLib --> Agent
	MetricExp --> Collector
	TraceCtx --> Collector
	Agent --> Collector
	Collector --> Obs
	Collector --> SIEM
	Obs --> Dash
```

### 6.5 Systems Maintenance Mechanisms View

```mermaid
---
title: Systems Management View - Systems Maintenance Mechanisms
---
flowchart LR
	subgraph Inputs[Maintenance Inputs and Governance]
		Vendor[Vendor advisories and approved packages]
		Vuln[Vulnerability and compliance findings]
		Change[Change calendar and maintenance windows]
		Baseline[Approved baselines and CMDB]
	end

	subgraph Maintenance[Maintenance Mechanisms]
		Repo[Patch and software repository]
		Dist[Software distribution tooling]
		Test[Non-production validation]
		Ring[Deployment rings or pilot groups]
		Rollback[Rollback and recovery plan]
	end

	subgraph Targets[Managed Targets]
		Endpoint[Client and admin endpoints]
		App[Application and middleware servers]
		DB[Database hosts]
		Tooling[Monitoring and management agents]
	end

	Vendor --> Repo
	Vuln --> Repo
	Baseline --> Test
	Repo --> Dist --> Test
	Test --> Ring
	Rollback --> Ring
	Change --> Ring
	Ring --> Endpoint
	Ring --> App
	Ring --> DB
	Ring --> Tooling
```

### 6.6 Supplier Remote Access View

```mermaid
---
title: Systems Management View - Supplier Remote Access
---
flowchart LR
	subgraph Request[Request and Approval]
		SupplierUser[Supplier engineer]
		Ticket[Support request or ticket]
		Approve[Customer approval and time-bound authorization]
		ServiceDesk[Service desk or duty manager]
	end

	subgraph AccessPath[Controlled Access Path]
		IdP[Identity provider and MFA]
		VPN[VPN or ZTNA service]
		PAM[Privileged access management]
		Jump[Jump host or bastion]
		Session[Recorded admin session]
	end

	subgraph Targets[Administrative Targets]
		App[Application servers]
		Infra[Platform and network administration endpoints]
		Mgmt[Management tooling]
	end

	subgraph Oversight[Oversight and Review]
		Log[Session logging and security monitoring]
		Review[Access review and revocation]
	end

	SupplierUser --> Ticket --> Approve
	ServiceDesk --> Approve
	Approve --> IdP --> VPN --> PAM --> Jump --> Session
	Session --> App
	Session --> Infra
	Session --> Mgmt
	Session --> Log
	PAM --> Review
	Log --> Review
```
