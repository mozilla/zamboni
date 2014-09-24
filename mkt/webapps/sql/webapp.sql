-- These are all the indexes you really need to run zamboni.  They're
-- explicitly used in queries.  We drop them all in one file because that's easy.

CREATE INDEX downloads_type_idx ON addons (weeklydownloads);
CREATE INDEX created_type_idx ON addons (created);
CREATE INDEX rating_type_idx ON addons (bayesianrating);
CREATE INDEX last_updated_type_idx ON addons (last_updated);
CREATE INDEX type_status_inactive_idx ON addons (status, inactive);
