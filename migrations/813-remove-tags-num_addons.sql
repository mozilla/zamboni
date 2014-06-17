-- Remove `num_addons` field from `Tags` model (bug 1026255).

alter table tags drop column num_addons;
