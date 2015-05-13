#!/usr/bin/env python

from mkt.constants import regions
from mkt.developers.cron import exclude_new_region


def run():
    exclude_new_region([
        regions.ABW, regions.AFG, regions.AGO, regions.AIA, regions.ALA,
        regions.ALB, regions.AND, regions.ARE, regions.ARM, regions.ASM,
        regions.ATA, regions.ATF, regions.ATG, regions.AUS, regions.AUT,
        regions.AZE, regions.BDI, regions.BEL, regions.BEN, regions.BES,
        regions.BFA, regions.BGR, regions.BHR, regions.BHS, regions.BIH,
        regions.BLM, regions.BLR, regions.BLZ, regions.BMU, regions.BOL,
        regions.BRB, regions.BRN, regions.BTN, regions.BVT, regions.CAN,
        regions.CCK, regions.CHE, regions.COD, regions.COG, regions.COK,
        regions.COM, regions.CPV, regions.CUB, regions.CUW, regions.CXR,
        regions.CYM, regions.CYP, regions.DJI, regions.DMA, regions.DNK,
        regions.DOM, regions.DZA, regions.ERI, regions.ESH, regions.EST,
        regions.ETH, regions.FIN, regions.FJI, regions.FLK, regions.FRO,
        regions.FSM, regions.GAB, regions.GEO, regions.GGY, regions.GHA,
        regions.GIB, regions.GLP, regions.GMB, regions.GNQ, regions.GRD,
        regions.GRL, regions.GUF, regions.GUM, regions.GUY, regions.HKG,
        regions.HMD, regions.HND, regions.HRV, regions.HTI, regions.IDN,
        regions.IMN, regions.IOT, regions.IRL, regions.IRQ, regions.ISL,
        regions.ISR, regions.JAM, regions.JEY, regions.KAZ, regions.KGZ,
        regions.KHM, regions.KIR, regions.KNA, regions.KOR, regions.KWT,
        regions.LAO, regions.LBN, regions.LBR, regions.LBY, regions.LCA,
        regions.LIE, regions.LKA, regions.LSO, regions.LUX, regions.LVA,
        regions.MAC, regions.MAF, regions.MAR, regions.MCO, regions.MDA,
        regions.MDV, regions.MHL, regions.MKD, regions.MLT, regions.MNG,
        regions.MNP, regions.MOZ, regions.MRT, regions.MSR, regions.MTQ,
        regions.MWI, regions.MYS, regions.MYT, regions.NAM, regions.NCL,
        regions.NFK, regions.NGA, regions.NIU, regions.NLD, regions.NOR,
        regions.NPL, regions.NRU, regions.NZL, regions.OMN, regions.PAK,
        regions.PCN, regions.PLW, regions.PNG, regions.PRI, regions.PRT,
        regions.PRY, regions.PSE, regions.PYF, regions.QAT, regions.REU,
        regions.ROU, regions.RWA, regions.SAU, regions.SDN, regions.SGP,
        regions.SGS, regions.SHN, regions.SJM, regions.SLB, regions.SLE,
        regions.SMR, regions.SOM, regions.SPM, regions.SSD, regions.STP,
        regions.SUR, regions.SVK, regions.SVN, regions.SWE, regions.SWZ,
        regions.SXM, regions.SYC, regions.SYR, regions.TCA, regions.TCD,
        regions.TGO, regions.THA, regions.TJK, regions.TKL, regions.TKM,
        regions.TLS, regions.TON, regions.TTO, regions.TUR, regions.TUV,
        regions.UGA, regions.UKR, regions.UMI, regions.UZB, regions.VAT,
        regions.VCT, regions.VGB, regions.VIR, regions.VNM, regions.WLF,
        regions.WSM, regions.YEM, regions.ZMB, regions.ZWE
    ])
