INSERT INTO groups (name, rules, created, modified, notes)
VALUES ('Website Reviewers', 'Websites:Review', NOW(), NOW(), 'Users who can review websites');
UPDATE groups SET rules=CONCAT(rules, ',Websites:Review') WHERE name = 'Staff';
