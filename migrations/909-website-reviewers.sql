INSERT INTO groups (id, name, rules, created, modified, notes)
VALUES (50080, 'Website Reviewers', 'Websites:Review', NOW(), NOW(), 'Users who can review websites');
UPDATE groups SET rules=CONCAT(rules, 'Websites:Review') WHERE name = 'Staff';
