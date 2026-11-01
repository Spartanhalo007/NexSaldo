-- PASO MANUAL (una sola vez, con la cuenta de administrador de PostgreSQL).
-- Ejecutar desde PowerShell en la raíz del proyecto:
--     psql -U postgres -f sql\preparar_base_datos.sql
--
-- Qué hace:
--   1. Pide por consola la contraseña del rol de la aplicación (\prompt),
--      de modo que la contraseña real nunca quede escrita en este archivo
--      ni en el historial de comandos de PowerShell.
--   2. Crea el rol nexsaldo_app: cuenta SIN privilegios de superusuario.
--   3. Crea la base de datos nexsaldo, propiedad de nexsaldo_app.
--   4. Retira a PUBLIC los privilegios sobre la base de datos: ninguna otra
--      cuenta local podrá conectarse a ella (endurecimiento de RNF-03).
--
-- La contraseña que escriba aquí debe ser la misma que configure en el
-- archivo .env local (NEXSALDO_DB_CONTRASENA).

\prompt 'Escriba la contraseña para el rol nexsaldo_app: ' contrasena_aplicacion

-- Aborta en el primer error y devuelve un código de fallo distinto de cero,
-- para que un problema no pase inadvertido.
\set ON_ERROR_STOP on

CREATE ROLE nexsaldo_app LOGIN PASSWORD :'contrasena_aplicacion';
CREATE DATABASE nexsaldo OWNER nexsaldo_app;
REVOKE ALL ON DATABASE nexsaldo FROM PUBLIC;
