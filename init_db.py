#!/usr/bin/env python3
"""
Script para inicializar la base de datos de Calculadora Eterno
"""
from app import init_db

if __name__ == '__main__':
    print("Inicializando base de datos...")
    init_db()
    print("✅ Base de datos inicializada correctamente")
    print("✅ Usuarios creados: admin y usuario")
    print("✅ Contraseña por defecto: eterno2026")
