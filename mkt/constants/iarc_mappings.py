import mkt.constants.ratingsbodies as ratingsbodies


# These mappings are required to convert the IARC response strings, like "ESRB"
# to the ratings body constants in mkt/constants/ratingsbodies. Likewise for
# the descriptors.
BODIES = {
    'classind': ratingsbodies.CLASSIND,
    'esrb': ratingsbodies.ESRB,
    'generic': ratingsbodies.GENERIC,
    'pegi': ratingsbodies.PEGI,
    'usk': ratingsbodies.USK,
    'default': ratingsbodies.GENERIC,
}


RATINGS = {
    ratingsbodies.CLASSIND.id: {
        'Livre': ratingsbodies.CLASSIND_L,
        '10+': ratingsbodies.CLASSIND_10,
        '12+': ratingsbodies.CLASSIND_12,
        '14+': ratingsbodies.CLASSIND_14,
        '16+': ratingsbodies.CLASSIND_16,
        '18+': ratingsbodies.CLASSIND_18,
        'default': ratingsbodies.CLASSIND_L,
    },
    ratingsbodies.ESRB.id: {
        'Everyone': ratingsbodies.ESRB_E,
        'Everyone 10+': ratingsbodies.ESRB_10,
        'Teen': ratingsbodies.ESRB_T,
        'Mature 17+': ratingsbodies.ESRB_M,
        'Adults Only': ratingsbodies.ESRB_A,
        'default': ratingsbodies.ESRB_E,
    },
    ratingsbodies.GENERIC.id: {
        '3+': ratingsbodies.GENERIC_3,
        '7+': ratingsbodies.GENERIC_7,
        '12+': ratingsbodies.GENERIC_12,
        '16+': ratingsbodies.GENERIC_16,
        '18+': ratingsbodies.GENERIC_18,
        'RP': ratingsbodies.GENERIC_RP,
        'default': ratingsbodies.GENERIC_3,
    },
    ratingsbodies.PEGI.id: {
        '3+': ratingsbodies.PEGI_3,
        '7+': ratingsbodies.PEGI_7,
        '12+': ratingsbodies.PEGI_12,
        '16+': ratingsbodies.PEGI_16,
        '18+': ratingsbodies.PEGI_18,
        'default': ratingsbodies.PEGI_3,
    },
    ratingsbodies.USK.id: {
        '0+': ratingsbodies.USK_0,
        '6+': ratingsbodies.USK_6,
        '12+': ratingsbodies.USK_12,
        '16+': ratingsbodies.USK_16,
        '18+': ratingsbodies.USK_18,
        'Rating Refused': ratingsbodies.USK_REJECTED,
        'default': ratingsbodies.USK_0,
    },
}


# WARNING: When adding a new rating descriptor here also include a migration.
#          All descriptor keys must be prefixed by the rating body (e.g. USK_).
#
# Together with DESCS_V2 below these are used to dynamically generate the field
# list for the RatingDescriptors Django model in mkt.webapps.models.
# (The model has both v1 and v2 keys, and it's fine, the extra keys are
#  simply irrelevant depending on the version).
DESCS = {
    ratingsbodies.CLASSIND.id: {
        u'Atos Crim\xEDnosos': 'has_classind_criminal_acts',
        u'Conte\xFAdo Sexual': 'has_classind_sex_content',
        u'Conte\xFAdo Impactante': 'has_classind_shocking',
        u'Drogas Il\xEDcitas': 'has_classind_drugs_illegal',
        u'Drogas L\xEDcitas': 'has_classind_drugs_legal',
        u'Drogas': 'has_classind_drugs',
        u'Linguagem Impr\xF3pria': 'has_classind_lang',
        u'Nudez': 'has_classind_nudity',
        u'Sexo': 'has_classind_sex',
        u'Sexo Expl\xEDcito': 'has_classind_sex_explicit',
        u'Viol\xEAncia Extrema': 'has_classind_violence_extreme',
        u'Viol\xEAncia': 'has_classind_violence',
    },

    ratingsbodies.ESRB.id: {
        u'Alcohol and Tobacco Reference': 'has_esrb_alcohol_tobacco_ref',
        u'Alcohol Reference': 'has_esrb_alcohol_ref',
        u'Animated Blood': 'has_esrb_animated_blood',
        u'Blood': 'has_esrb_blood',
        u'Blood and Gore': 'has_esrb_blood_gore',
        u'Cartoon Violence': 'has_esrb_cartoon_violence',
        u'Comic Mischief': 'has_esrb_comic_mischief',
        u'Crime': 'has_esrb_crime',
        u'Criminal Instruction': 'has_esrb_crime_instruct',
        u'Crude Humor': 'has_esrb_crude_humor',
        u'Drug and Alcohol Reference': 'has_esrb_drug_alcohol_ref',
        u'Drug and Tobacco Reference': 'has_esrb_drug_tobacco_ref',
        u'Drug Reference': 'has_esrb_drug_ref',
        u'Drug, Alcohol and Tobacco Reference':
            'has_esrb_drug_alcohol_tobacco_ref',
        u'Fantasy Violence': 'has_esrb_fantasy_violence',
        u'Hate Speech': 'has_esrb_hate_speech',
        u'Intense Violence': 'has_esrb_intense_violence',
        u'Language': 'has_esrb_lang',
        u'Lyrics': 'has_esrb_lyrics',
        u'Mature Humor': 'has_esrb_mature_humor',
        u'Mild Blood': 'has_esrb_mild_blood',
        u'Mild Cartoon Violence': 'has_esrb_mild_cartoon_violence',
        u'Mild Fantasy Violence': 'has_esrb_mild_fantasy_violence',
        u'Mild Language': 'has_esrb_mild_lang',
        u'Mild Lyrics': 'has_esrb_mild_lyrics',
        u'Mild Sexual Content': 'has_esrb_mild_sexual_content',
        u'Mild Sexual Themes ': 'has_esrb_mild_sexual_themes',
        u'Mild Suggestive Themes ': 'has_esrb_mild_suggestive_themes',
        u'Mild Violence': 'has_esrb_mild_violence',
        u'Nudity': 'has_esrb_nudity',
        u'Partial Nudity': 'has_esrb_partial_nudity',
        u'Real Gambling': 'has_esrb_real_gambling',
        u'Scary Themes': 'has_esrb_scary',
        u'Sexual Content': 'has_esrb_sex_content',
        u'Sexual Themes': 'has_esrb_sex_themes',
        u'Sexual Violence': 'has_esrb_sex_violence',
        u'Simulated Gambling': 'has_esrb_sim_gambling',
        u'Strong Language': 'has_esrb_strong_lang',
        u'Strong Lyrics': 'has_esrb_strong_lyrics',
        u'Strong Sexual Content': 'has_esrb_strong_sex_content',
        u'Suggestive Themes': 'has_esrb_suggestive',
        u'Tobacco Reference': 'has_esrb_tobacco_ref',
        u'Use of Alcohol': 'has_esrb_alcohol_use',
        u'Use of Alcohol and Tobacco': 'has_esrb_alcohol_tobacco_use',
        u'Use of Drug and Alcohol': 'has_esrb_drug_alcohol_use',
        u'Use of Drug and Tobacco': 'has_esrb_drug_tobacco_use',
        u'Use of Drug, Alcohol and Tobacco':
            'has_esrb_drug_alcohol_tobacco_use',
        u'Use of Drugs': 'has_esrb_drug_use',
        u'Use of Tobacco': 'has_esrb_tobacco_use',
        u'Violence': 'has_esrb_violence',
        u'Violent References': 'has_esrb_violence_ref',
    },

    ratingsbodies.GENERIC.id: {
        u'Discrimination': 'has_generic_discrimination',
        u'Drugs': 'has_generic_drugs',
        u'Fear': 'has_generic_scary',
        u'Gambling': 'has_generic_gambling',
        u'Language': 'has_generic_lang',
        u'Online': 'has_generic_online',
        u'Sex': 'has_generic_sex_content',
        u'Violence': 'has_generic_violence',
    },

    ratingsbodies.PEGI.id: {
        u'Discrimination': 'has_pegi_discrimination',
        u'Drugs': 'has_pegi_drugs',
        u'Fear': 'has_pegi_scary',
        u'Gambling': 'has_pegi_gambling',
        u'Horror': 'has_pegi_horror',
        u'Language': 'has_pegi_lang',
        u'Online': 'has_pegi_online',
        u'Sex': 'has_pegi_sex_content',
        u'Violence': 'has_pegi_violence',

        # PEGI's versions of Interactive Elements.
        u'In-app purchase option': 'has_pegi_digital_purchases',
        u'Location data sharing': 'has_pegi_shares_location',
        u'Personal data sharing': 'has_pegi_shares_info',
        u'Social interaction functionality': 'has_pegi_users_interact',
    },

    ratingsbodies.USK.id: {
        u'Alkoholkonsum': 'has_usk_alcohol',
        u'Abstrakte Gewalt': 'has_usk_abstract_violence',
        u'Andeutungen Sexueller Gewalt': 'has_usk_sex_violence_ref',
        u'\xC4ngstigende Inhalte': 'has_usk_scary',
        u'Diskriminierung': 'has_usk_discrimination',
        u'Drogen': 'has_usk_drugs',
        u'Drogenkonsum': 'has_usk_drug_use',
        u'Erotik/Sexuelle Inhalte': 'has_usk_sex_content',
        u'Explizite Sprache': 'has_usk_lang',
        u'Explizite Gewalt': 'has_usk_explicit_violence',
        u'Gelegentliches Fluchen': 'has_usk_some_swearing',
        u'Gewalt': 'has_usk_violence',
        u'Grusel/Horror': 'has_usk_horror',
        u'Nacktheit/Erotik': 'has_usk_nudity',
        u'Seltene Schreckmomente': 'has_usk_some_scares',
        u'Sexuelle Gewalt': 'has_usk_sex_violence',
        u'Sexuelle Andeutungen': 'has_usk_sex_ref',
        u'Tabakkonsum': 'has_usk_tobacco',
    },
}

# WARNING: When adding a new rating descriptor here also include a migration.
#          All descriptor keys must be prefixed by the rating body (e.g. USK_).
#
# Together with DESCS above these are used to dynamically generate the field
# list for the RatingDescriptors Django model in mkt.webapps.models.
# (The model has both v1 and v2 keys, and it's fine, the extra keys are
#  simply irrelevant depending on the version).
DESCS_V2 = {
    ratingsbodies.CLASSIND.id: {
        'ClassInd_AtosCriminosos': 'has_classind_criminal_acts',
        'ClassInd_ConteudoImpactante': 'has_classind_shocking',
        'ClassInd_ConteudoSexual': 'has_classind_sex_content',
        'ClassInd_Drogas': 'has_classind_drugs',
        'ClassInd_DrogasIlicitas': 'has_classind_drugs_illegal',
        'ClassInd_DrogasLicitas': 'has_classind_drugs_legal',
        'ClassInd_LinguagemImpropria': 'has_classind_lang',
        'ClassInd_Naohainadequacoes': '',  # No descriptors.
        'ClassInd_Nudez': 'has_classind_nudity',
        'ClassInd_Sexo': 'has_classind_sex',
        'ClassInd_SexoExplicito': 'has_classind_sex_explicit',
        'ClassInd_Violencia': 'has_classind_violence',
        'ClassInd_ViolenciaExtrema': 'has_classind_violence_extreme',
    },

    ratingsbodies.ESRB.id: {
        'ESRB_AlcoholandTobaccoReference': 'has_esrb_alcohol_tobacco_ref',
        'ESRB_AlcoholReference': 'has_esrb_alcohol_tobacco_ref',
        'ESRB_AnimatedBlood': 'has_esrb_animated_blood',
        'ESRB_Blood': 'has_esrb_blood',
        'ESRB_BloodandGore': 'has_esrb_blood_gore',
        'ESRB_CartoonViolence': 'has_esrb_cartoon_violence',
        'ESRB_ComicMischief': 'has_esrb_comic_mischief',
        'ESRB_CrudeHumor': 'has_esrb_crude_humor',
        'ESRB_DiverseContentDiscretionAdvised': '',
        'ESRB_DrugAlcoholandTobaccoReference':
            'has_esrb_drug_alcohol_tobacco_ref',
        'ESRB_DrugandAlcoholReference': 'has_esrb_drug_alcohol_ref',
        'ESRB_DrugandTobaccoReference': 'has_esrb_drug_tobacco_ref',
        'ESRB_DrugReference': 'has_esrb_drug_ref',
        'ESRB_FantasyViolence': 'has_esrb_fantasy_violence',
        'ESRB_IntenseViolence': 'has_esrb_intense_violence',
        'ESRB_Language': 'has_esrb_lang',
        'ESRB_Lyrics': 'has_esrb_lyrics',
        'ESRB_MatureHumor': 'has_esrb_mature_humor',
        'ESRB_MildBlood': 'has_esrb_mild_blood',
        'ESRB_MildCartoonViolence': 'has_esrb_mild_cartoon_violence',
        'ESRB_MildFantasyViolence': 'has_esrb_mild_fantasy_violence',
        'ESRB_MildLanguage': 'has_esrb_mild_lang',
        'ESRB_MildLyrics': 'has_esrb_mild_lyrics',
        'ESRB_MildSexualContent': 'has_esrb_mild_sexual_content',
        'ESRB_MildSexualThemes': 'has_esrb_mild_sexual_themes',
        'ESRB_MildSuggestiveThemes': 'has_esrb_mild_suggestive_themes',
        'ESRB_MildViolence': 'has_esrb_mild_violence',
        'ESRB_NoDescriptors': '',  # No Descriptors.
        'ESRB_Nudity': 'has_esrb_nudity',
        'ESRB_PartialNudity': 'has_esrb_partial_nudity',
        'ESRB_RealGambling': 'has_esrb_real_gambling',
        'ESRB_SexualContent': 'has_esrb_sex_content',
        'ESRB_SexualThemes': 'has_esrb_sex_themes',
        'ESRB_SexualViolence': 'has_esrb_sex_violence',
        'ESRB_SimulatedGambling': 'has_esrb_sim_gambling',
        'ESRB_StrongLanguage': 'has_esrb_strong_lang',
        'ESRB_StrongLyrics': 'has_esrb_strong_lyrics',
        'ESRB_StrongSexualContent': 'has_esrb_strong_sex_content',
        'ESRB_SuggestiveThemes': 'has_esrb_suggestive',
        'ESRB_TobaccoReference': 'has_esrb_tobacco_ref',
        'ESRB_UseofAlcohol': 'has_esrb_alcohol_use',
        'ESRB_UseofAlcoholandTobacco': 'has_esrb_alcohol_tobacco_use',
        'ESRB_UseofDrugs': 'has_esrb_drug_use',
        'ESRB_UseofDrugsAlcoholandTobacco':
            'has_esrb_drug_alcohol_tobacco_use',
        'ESRB_UseofDrugsandAlcohol': 'has_esrb_drug_alcohol_use',
        'ESRB_UseofDrugsandTobacco': 'has_esrb_drug_tobacco_use',
        'ESRB_UseofTobacco': 'has_esrb_tobacco_use',
        'ESRB_Violence': 'has_esrb_violence',
        'ESRB_ViolentReferences': 'has_esrb_violence_ref',
    },

    ratingsbodies.GENERIC.id: {
        # Yes, "Generic" seems to be using PEGI descriptors for some reason.
        'PEGI_Discrimination': 'has_generic_discrimination',
        'PEGI_Drugs': 'has_generic_drugs',
        'PEGI_Fear': 'has_generic_scary',
        'PEGI_Gambling': 'has_generic_gambling',
        'PEGI_Language': 'has_generic_lang',
        'PEGI_Online': 'has_generic_online',
        'PEGI_Sex': 'has_generic_sex_content',
        'PEGI_Violence': 'has_generic_violence',
    },

    ratingsbodies.PEGI.id: {
        'PEGI_CriminalTechniqueInstructions': '',
        'PEGI_Discrimination': 'has_pegi_discrimination',
        'PEGI_Drugs': 'has_pegi_drugs',
        'PEGI_ExtremeViolence': '',
        'PEGI_Fear': 'has_pegi_scary',
        'PEGI_Gambling': 'has_pegi_gambling',
        'PEGI_Horror': 'has_pegi_horror',
        'PEGI_ImpliedViolence': '',
        'PEGI_Language': 'has_pegi_lang',
        'PEGI_MildSwearing': '',
        'PEGI_MildViolence': '',
        'PEGI_ModerateViolence': '',
        'PEGI_NoDescriptors': '',  # No descriptors.
        'PEGI_Online': 'has_pegi_online',
        'PEGI_ParentalGuidanceRecommended': '',
        'PEGI_Sex': 'has_pegi_sex_content',
        'PEGI_SexualInnuendo': '',
        'PEGI_SexualViolence': '',
        'PEGI_StrongLanguage': '',
        'PEGI_StrongViolence': '',
        'PEGI_UseofAlcoholTobacco': '',
        'PEGI_Violence': 'has_pegi_violence',
    },

    ratingsbodies.USK.id: {
        'USK_AbstrakteGewalt': 'has_usk_abstract_violence',
        'USK_Alkoholkonsum': 'has_usk_alcohol',
        'USK_AndeutungenSexuellerGewalt': 'has_usk_sex_violence_ref',
        'USK_AngstigendeInhalte': 'has_usk_scary',
        'USK_Diskriminierung': 'has_usk_discrimination',
        'USK_Drogenkonsum': 'has_usk_drug_use',
        'USK_ExpliziteGewalt': 'has_usk_explicit_violence',
        'USK_ExpliziteSprache': 'has_usk_lang',
        'USK_GelegentlichesFluchen': 'has_usk_some_swearing',
        'USK_Gewalt': 'has_usk_violence',
        'USK_GruselHorror': 'has_usk_horror',
        'USK_NacktheitErotik': 'has_usk_nudity',
        'USK_NoDescriptors': '',    # No Descriptors.
        'USK_SelteneSchreckmomente': 'has_usk_some_scares',
        'USK_SexErotik': 'has_usk_sex_content',  # 'Erotik/Sexuelle Inhalte'.
        'USK_SexuelleAndeutungen': 'has_usk_sex_ref',
        'USK_SexuelleGewalt': 'has_usk_sex_violence',
        'USK_ShopStreamingService': '',
        'USK_Tabakkonsum': 'has_usk_tobacco',
    }

}

# Change {body: {'key': 'val'}} to {'val': 'key'}, combining v1 and v2 dicts.
_REVERSE_DESCS_BY_BODY = [
    {unicode(v): unicode(k) for k, v in body_mapping.items() if v}
    for body, body_mapping in DESCS_V2.items() + DESCS.items()]
REVERSE_DESCS = {}
for mapping in _REVERSE_DESCS_BY_BODY:
    REVERSE_DESCS.update(mapping)

# WARNING: When adding a new interactive element here also include a migration.
#
# These are used to dynamically generate the field list for the
# RatingInteractives django model in mkt.webapps.models.
INTERACTIVES = {
    'Users Interact': 'has_users_interact',
    'Shares Info': 'has_shares_info',
    'Shares Location': 'has_shares_location',
    'Digital Purchases': 'has_digital_purchases',
}

INTERACTIVES_V2 = {
    'IE_UsersInteract': 'has_users_interact',
    'IE_SharesInfo': 'has_shares_info',
    'IE_SharesLocation': 'has_shares_location',
    'IE_DigitalPurchases': 'has_digital_purchases',
}

REVERSE_INTERACTIVES = {v: k for k, v
                        in INTERACTIVES_V2.items() + INTERACTIVES.items()}
