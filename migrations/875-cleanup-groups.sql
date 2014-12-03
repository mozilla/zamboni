UPDATE groups SET rules='Apps:*,Users:Edit,Stats:View,AdminTools:View,AccountLookup:View,AppLookup:View,Lookup:View,Stats:View' WHERE name='Staff';
UPDATE groups SET rules='Stats:View' WHERE name='Statistic Viewers';
UPDATE groups SET rules='Apps:Review' WHERE name='App Reviewers';
UPDATE groups SET rules='Apps:Review,Apps:Edit,ReviewerAdminTools:View,Apps:ReviewEscalated,Apps:ReviewPrivileged,Apps:ReviewRegionCN' WHERE name='Senior App Reviewers';
UPDATE groups SET rules='Prices:Edit' WHERE name='Price currency manipulation';
-- The 'groups_users' table has ON DELETE CASCADE for the group so this will take care of business.
DELETE FROM groups WHERE name in ('Add-on Reviewers', 'Persona Reviewers', 'Senior Add-on Reviewers',
    'Add-on Reviewer MOTD', 'Persona Reviewer MOTD', 'OAuth Partner: Flightdeck',
    'Bulk Compatibility Updaters', 'Feature Managers', 'Developers Credits',
    'Past Developers Credits', 'Other Contributors Credits');
