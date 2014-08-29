-- Remove all file_uploads related to AMO extensions.
DELETE FROM file_uploads WHERE name like '%.xpi' OR name like '%.jar' OR name like '%.xml';
