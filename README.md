# Mealoo Backend Documentation

---

# Project Overview

Mealoo is a hyperlocal digital meal/tiffin platform backend system.

The current backend implementation focuses on provider onboarding and authentication using mobile OTP verification.

Current completed modules:
- Provider Registration
- OTP Generation
- OTP Verification
- Forgot Password using OTP verification

---

# Tech Stack

| Technology | Purpose |
|---|---|
| FastAPI | Backend framework |
| PostgreSQL | Database |
| SQLAlchemy | ORM |
| Pydantic | Request/Response validation |
| Passlib/Bcrypt | Password hashing |
| JWT | Planned authentication |

---

# Current Authentication Flow

## Provider Registration Flow

Provider Registration
    ↓
OTP Generation
    ↓
OTP Verification
    ↓
Provider Creation

---

## Forgot Password Flow

Forgot Password Request
    ↓
OTP Generation
    ↓
OTP Verification
    ↓
Existing Provider Password Updated

---

# Folder Structure

```text
app/
│
├── api/
│   └── v1/
│       └── endpoints/
│
├── core/
│
├── middleware/
│
├── models/
│
├── repositories/
│
├── schemas/
│
├── services/
│
├── utils/
│
└── main.py
Architecture

The backend follows Repository-Service layered architecture.

Request Flow:

API Endpoint
    ↓
Service Layer
    ↓
Repository Layer
    ↓
SQLAlchemy Models
    ↓
PostgreSQL Database
Layer Responsibilities
API Layer

Location:

app/api/v1/endpoints/

Responsibilities:

Handle HTTP requests
Handle responses
Request validation
Route management
Service Layer

Location:

app/services/

Responsibilities:

Business logic
Authentication flow
OTP validation
Password update logic
Provider creation flow
Repository Layer

Location:

app/repositories/

Responsibilities:

Database queries
CRUD operations
Table-specific operations
Models Layer

Location:

app/models/

Responsibilities:

SQLAlchemy ORM models
Database table mapping
Schemas Layer

Location:

app/schemas/

Responsibilities:

Pydantic validation
Request schemas
Response schemas
Database Schema
providers table

Purpose:
Stores provider account and profile information.

Column	Type	Description
id	bigint	Primary key
mobile_number	varchar	Unique provider mobile number
is_mobile_verified	boolean	Mobile verification status
is_profile_completed	boolean	Profile completion status
full_name	varchar	Provider full name
business_name	varchar	Business name
city	varchar	City
area	varchar	Area
address	text	Full address
kitchen_type	varchar	Kitchen category
profile_image	varchar	Provider profile image
created_at	timestamp	Record creation timestamp
updated_at	timestamp	Record update timestamp
provider_id	varchar	Unique provider reference
hashed_password	varchar	Bcrypt hashed password
pincode	integer	Area pincode
house_no	integer	House number
landmark	varchar	Address landmark
state	varchar	State
otp_logs table

Purpose:
Stores OTP verification logs.

Used for:

Registration
Forgot Password
Column	Type	Description
otp_log_id	bigint	Primary key
mobile_number	varchar	Mobile number
otp	varchar	Generated OTP
expires_at	timestamp	OTP expiry time
is_verified	boolean	OTP verification status
attempts	integer	Invalid attempt count
created_at	timestamp	OTP creation time
hashed_password	varchar	Temporarily stored password hash
Current Implemented APIs
POST /auth/send-otp

Purpose:
Generate OTP for provider registration or forgot password.

Request
{
    "mobile_number": "9999999999",
    "password": "Test@123"
}
Response
{
    "success": true,
    "message": "OTP sent successfully"
}
Database Tables Used
otp_logs
Services Used
otp_service.py
Repository Used
otp_repository.py
POST /auth/verify-otp

Purpose:
Verify OTP and:

create provider if not exists
update password if provider already exists
Request
{
    "mobile_number": "9999999999",
    "otp": "123456"
}
Response
{
    "success": true,
    "message": "OTP verified successfully",
    "provider_id": "PROVIDER_001",
    "is_profile_completed": false
}
Verification Checks

The API validates:

OTP existence
OTP expiry
OTP verification status
OTP attempt count
Database Tables Used
otp_logs
providers
Services Used
auth_service.py
Repository Used
otp_repository.py
provider_repository.py
File Responsibilities
app/models/provider_model.py

Purpose:
Stores provider profile and authentication information.

Important Fields:

mobile_number
hashed_password
is_profile_completed
is_mobile_verified
app/models/otp_log_model.py

Purpose:
Stores OTP verification records.

Important Fields:

otp
expires_at
attempts
hashed_password
app/services/auth_service.py

Responsibilities:

Provider registration logic
OTP verification logic
Forgot password flow
Provider creation
Password update logic

Dependencies:

otp_repository.py
provider_repository.py

Database Tables:

providers
otp_logs
app/services/otp_service.py

Responsibilities:

OTP generation
OTP expiration handling
OTP validation support
app/repositories/provider_repository.py

Responsibilities:

Create provider
Get provider by mobile number
Update provider password
Provider database operations
app/repositories/otp_repository.py

Responsibilities:

Store OTP records
Fetch latest OTP
Update OTP verification status
app/core/security.py

Responsibilities:

Password hashing
Password verification
Security utilities
app/utils/otp_generator.py

Responsibilities:

Generate random OTPs
Security Implementation

Current security mechanisms:

Password hashing using bcrypt
OTP expiration validation
OTP attempt tracking
OTP verification status check
Current Business Logic
New Provider Flow

If provider does not exist:

OTP verified
New provider created
Mobile marked verified
Profile marked incomplete
Existing Provider Flow

If provider already exists:

OTP verified
Existing password updated
Used for forgot password functionality
Future Planned Modules
Authentication
JWT Authentication
Refresh Token
Access Token Middleware
Provider Module
Profile Completion API
Kitchen Setup API
Address Management API
Profile Image Upload
Meal System
Meal Management
Menu Management
Meal Scheduling
Subscription System
Subscription Plans
Daily Meal Booking
Subscription Renewal
Order System
Order Placement
Order Tracking
Order History
Delivery System
Delivery Partner Management
Live Tracking
Delivery Status
Future Recommended Improvements
OTP Improvements
Add OTP purpose field
Add rate limiting
Add resend OTP limit
Security Improvements
JWT authentication
Refresh token rotation
Device session management
Database Improvements
Add foreign key relationships
Add indexing optimization
Add soft delete support
Current Development Status
Module	Status
Provider Registration	Completed
OTP Generation	Completed
OTP Verification	Completed
Forgot Password Flow	Completed
JWT Login	Pending
Provider Profile APIs	Pending
Meal APIs	Pending
Order APIs	Pending
Important Notes

Current system architecture is designed to be:

scalable
modular
reusable
repository-service based

The documentation is intentionally detailed so future modifications can be implemented using only this README without requiring the complete source code initially.

have you merge all reccomended md files to this readme.md ?

Yes.
The single README.md I created already merges the content and responsibilities of all recommended documentation files into one master document.

It includes merged sections from:

Recommended File	Merged Into README.md
project-overview.md	✅ Project Overview
architecture.md	✅ Architecture + Layer Responsibilities
auth-flow.md	✅ Authentication Flow
database-schema.md	✅ Database Schema
api-reference.md	✅ Current Implemented APIs
folder-structure.md	✅ Folder Structure
provider-module.md	✅ File Responsibilities + Provider Flow
otp-flow.md	✅ OTP Verification Logic
future-roadmap.md	✅ Future Planned Modules
changelog.md	Partially via Development Status
Your Current README.md Already Contains
Business Understanding
What Mealoo is
Current implemented modules
Future modules
Technical Architecture
Layered architecture
Request lifecycle
Repository-service pattern
Database Understanding
providers table
otp_logs table
important fields
future scalability understanding
API Understanding
endpoints
request/response
business purpose
DB impact
services/repositories used
File-Level Understanding
service responsibilities
repository responsibilities
model responsibilities
utility responsibilities
Authentication Logic
registration flow
OTP flow
forgot password flow
Future Scalability
JWT
refresh token
delivery system
subscriptions
meal management
This Is Exactly Why It Is Powerful

Later you can simply send ONLY:

README.md

and I can still understand:

overall backend structure,
architecture,
DB flow,
auth logic,
dependencies,
extension points,
impacted files.
What Is Still Missing (Later)

As your project grows, later you may additionally add:

1. ER Diagram Section

DB relationships.

2. Environment Variables Section

Example:

DATABASE_URL=
JWT_SECRET=
OTP_EXPIRY=
3. Deployment Section
Docker
Nginx
Gunicorn/Uvicorn
CI/CD
4. API Versioning Strategy
5. Naming Conventions
Current README Quality

Your current merged README is already enough for:

future AI-assisted development,
onboarding developers,
architecture understanding,
scalable extension planning.

For your current project stage, this is a very good foundation.