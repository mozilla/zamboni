DELETE FROM waffle_switch WHERE name = 'firefox-accounts';
INSERT INTO waffle_switch (name, active, note, created, modified)
    VALUES ('native-firefox-accounts', 0,
            'Enables use of native FxA on FxOS 2.1 and later'
            , NOW(), NOW());
