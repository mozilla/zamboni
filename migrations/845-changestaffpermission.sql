-- Simplify Staff rules.  Leaving Addons:* in for now until bug 1025073 is completed.
UPDATE groups SET rules='Addons:*,Apps:*,FeaturedApps:*,Reviews:Edit,Users:Edit,Stats:View,CollectionStats:View,Collections:Edit,AdminTools:View,AccountLookup:View,AppLookup:View,Lookup:View,Stats:View' WHERE name='Staff' AND id >= 50000;
