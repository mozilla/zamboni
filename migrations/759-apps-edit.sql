UPDATE groups SET rules=CONCAT(rules, ',Apps:Edit')
WHERE name='Staff' OR name='Senior App Reviewers';
