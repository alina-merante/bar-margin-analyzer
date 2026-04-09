# Bar Margin Analyzer — Architecture

Backend and data processing service for the Bar Margin Analyzer project.

## Overview

The system ingests sales (POS) and bank transaction data, classifies expenses using rule-based categorization, and exposes financial analytics via REST APIs.

## Tech Stack

- Backend: FastAPI
- Database: PostgreSQL
- ORM: SQLAlchemy
- Migrations: Alembic
- Containerization: Docker Compose

## Project Structure

backend/
  app/
    main.py              # FastAPI entrypoint
    database.py          # DB session + engine
    models.py            # SQLAlchemy models
    routers/
      imports.py         # CSV import endpoints
      analytics.py       # Financial analytics
      invoices.py        # Invoice & payment tracking
      categories.py      # Categories and rules

frontend/
  src/
    App.jsx              # Dashboard UI
    components/          # UI components
    styles/              # CSS

data/
  pos_*.csv              # Demo POS data
  bank_*.csv             # Demo bank data

docker-compose.yml

## Core Concepts

### Sales (POS)

- Stored in SaleLine
- Fields: date, product_id, qty, total
- Represent revenue

---

### Bank Transactions

- Stored in Transaction
- Fields: date, description, amount, counterparty, category_id
- Negative values = expenses
- Positive values are ignored

---

### Categories and Rules

- Categories define expense types (e.g. "Bevande", "Utenze")
- Rules map keywords to categories

Example:

{
  "keyword": "METRO",
  "category_id": 1
}

Rules are applied during /imports/bank-csv.

---

### Invoices & Payments

- Invoices track supplier costs and due dates
- Payments can be linked manually
- Status automatically updates to paid

---

### Analytics

Main endpoints:

- /analytics/pnl
- /analytics/pnl/trend
- /analytics/overview
- /analytics/expenses-by-category
- /analytics/expenses-by-supplier
- /analytics/insights

### Business Logic

- Revenue = sum of SaleLine.total
- Expenses = absolute value of negative Transaction.amount
- Profit = revenue - expenses

---

## Data Flow

CSV (POS / Bank)
      ↓
Import API
      ↓
Database (PostgreSQL)
      ↓
Analytics layer
      ↓
Frontend Dashboard

---

## Run the System

docker compose up --build

API:

- http://localhost:8000
- http://localhost:8000/docs
