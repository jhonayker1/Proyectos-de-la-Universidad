import sys
import os
import uvicorn

# Añade la carpeta raíz del proyecto a las rutas de búsqueda de Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importa la instancia directamente en lugar de usar cadenas de texto
from app.core.config import settings
from app.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=settings.PORT)



#python -m uvicorn app.main:app --reload