# PhD Timeline Intelligence Platform

A production-ready platform for managing and optimizing PhD research timelines with intelligent insights.

## Tech Stack

### Frontend
- React 18
- Vite
- TypeScript
- TailwindCSS

### Backend
- FastAPI (Python 3.11+)
- PostgreSQL
- SQLAlchemy ORM

### Infrastructure
- Docker & Docker Compose
- PostgreSQL Database

## Project Structure

```
.
├── frontend/          # React + Vite + TypeScript frontend
├── backend/           # FastAPI Python backend
├── resources/         # Project documentation, PRDs, diagrams
├── infra/            # Infrastructure configuration
└── README.md
```

## Getting Started

### Prerequisites
- Node.js 18+ and npm/yarn
- Python 3.11+
- Docker and Docker Compose
- PostgreSQL 15+

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/frenseiphdpeer-star/Phdpeer-Backend.git
   cd Phdpeer-Backend
   ```

2. **Start with Docker Compose**
   ```bash
   docker-compose up -d
   ```

3. **Frontend Development**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. **Backend Development**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

## Documentation

See the `/resources` folder for:
- Product Requirements Documents (PRDs)
- Architecture diagrams
- API documentation
- Development guides

## License

[Add your license here]
