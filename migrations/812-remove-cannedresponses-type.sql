-- Remove `CannedResponse` `type` for add-ons vs. apps (bug 1021837).

delete from cannedresponses where type=1;
alter table cannedresponses drop column type;
