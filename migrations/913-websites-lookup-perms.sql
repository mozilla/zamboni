-- Changing Websites:Review to Websites:* and removing duplicate Stats:View.
UPDATE groups SET rules='Apps:*,Websites:*,Users:Edit,Stats:View,AdminTools:View,AccountLookup:View,AppLookup:View,Lookup:View' WHERE name='Staff';
UPDATE groups SET rules=CONCAT(rules, ',WebsiteLookup:View') WHERE name IN ('Staff', 'Support Staff', 'Carriers and Operators');
