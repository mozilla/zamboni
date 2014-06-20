-- When the Review model moved from apps/reviews/ to mkt/ratings/ the django
-- app_label changed. We use the app_label + model_name to refer to activity
-- log relationships, and the move broke points to Reviews.

UPDATE log_activity
SET arguments=REPLACE(arguments, '"reviews.review"', '"ratings.review"')
WHERE action IN (29, 40, 41, 107);
