-- PASO MANUAL (una sola vez, con la cuenta de administrador de PostgreSQL).
-- Ejecutar desde PowerShell en la raíz del proyecto:
--     psql -U postgres -f sql\preparar_base_datos.sql
--
-- Crea:
--   1. El rol nexsaldo_app: cuenta SIN privilegios de superusuario. Solo
--      puede iniciar sesión y trabajar dentro de la base de datos nexsaldo.
--   2. La base de datos nexsaldo, propiedad de nexsaldo_app.
--
-- IMPORTANTE:
-- - Reemplace CAMBIAR_ESTA_CONTRASENA por una contraseña propia ANTES de
--   ejecutar este archivo.
-- - No registre esa contraseña en el repositorio: la que usa la aplicación
--   se configura en el archivo .env local (ver .env.example).

CREATE ROLE nexsaldo_app LOGIN PASSWORD 'CAMBIAR_ESTA_CONTRASENA';
CREATE DATABASE nexsaldo OWNER nexsaldo_app;
