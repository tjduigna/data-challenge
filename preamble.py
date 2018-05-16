#!/usr/bin/env python3
# The basics
import os
import numexpr        # Only required for fast df slice
import requests
import numpy as np
import pandas as pd
import seaborn as sns
imshow = sns.mpl.pyplot.imshow
from collections import defaultdict
import lxml           # Not used but required by pandas
# Testing naive database performances
import psycopg2
import pymongo
from sqlalchemy import (
        create_engine, Float, Column,
        MetaData, Table, Integer, String,)
from sqlalchemy.orm import sessionmaker



# URLs for quick access to governmental data
bls_url = 'https://www.bls.gov/cew/cewedr10.htm'
census_url = 'https://api.census.gov/data'
cen_query = 'pep/subcty?get=NAME,STNAME,CTYNAME,POP&{}'.format
national_url = '{}/{{year}}/'



# Your paths may vary
prim = '../notebooks/data-challenge/'
base = (prim + 'nsduh/NSDUH-{0}-DS0001-data/'
        'NSDUH-{0}-DS0001-data-excel.tsv')
dbase = (prim + 'partd/PartD_Prescriber_'
         'PUF_NPI_Drug_{}.txt')
sbase = (prim + 'partd/PartD_Prescriber_'
         'PUF_NPI_{}.txt')
paths = {key: base.format(key) for key in range(2011, 2017)}
dpaths = {2000 + key: dbase.format(key) for key in range(13, 17)}
spaths = {2000 + key: sbase.format(key) for key in range(13, 17)}

# Medicare Part D META DATA

partdtypes = {
    'npi':                             np.int64,
    'nppes_provider_last_org_name':      object,
    'nppes_provider_first_name':         object,
    'nppes_provider_city':           'category',
    'nppes_provider_state':              object,
    'specialty_description':             object,
    'description_flag':              'category',
    'drug_name':                         object,
    'generic_name':                      object,
    'bene_count':                    np.float64,
    'total_claim_count':               np.int64,
    'total_30_day_fill_count':       np.float64,
    'total_day_supply':                np.int64,
    'total_drug_cost':               np.float64,
    'bene_count_ge65':               np.float64,
    'bene_count_ge65_suppress_flag': 'category',
    'total_claim_count_ge65':        np.float64,
    'ge65_suppress_flag':            'category',
    'total_30_day_fill_count_ge65':  np.float64,
    'total_day_supply_ge65':         np.float64,
    'total_drug_cost_ge65':          np.float64,
}

# Generic names of marijuana derived prescriptions
mjps = [
    # Directly found in marijuana
    'DRONABINOL',
    'MARINOL',
    'THC',
    'SATIVEX',
    # Cannabinoids not found in marijuana
    'NABILONE',
    'CESAMET',
]



# NSDUH META DATA
# 2016 didn't come with as much auxiliary info
demographic = [ # Notes that map entries to actual values
    'INCOME',   # 1: <20k, 2: 20k-50, 3: 50k-75k, 4: >75k
    'ANYHLTI2', # Covered by health insurance
    'AGE2',     # 1-10: 12-21, 11: 22-23, 12: 24-25,
                # 13: 26-29, 14: 30-34, 15: 35-49, 16: 50-64, 17: >64
    'SERVICE',  # 1: Been in armed forces, 2: No
    'HEALTH',   # 1: Excellent, 2: Very good, 3: Good, 4: Fair, 5: Poor
    # Redundant and may be removed from subsequent analysis
    'CATAGE',   # 1: 12-17, 2: 18-25, 3: 26-34, 4: >34
    'CATAG2',   # 1: 12-17, 2: 18-25, 3: >25
    'CATAG3',   # 1: 12-17, 2: 18-25, 3: 26-34, 
                # 4: 35-49, 5: >49
    'CATAG6',   # 1: 12-17, 2: 18-25, 3: 26-34, 
                # 4: 35-49, 5: 50-64, 6: >64
    'CATAG7',   # 1: 12-13, 2: 14-15, 3: 16-17, 4: 18-20, 
                # 5: 21-25, 6: 26-34, 7: >34
]


prefixes = [
    'ALC',   # Alcohol
    'MJ',    # Marijuana
    'CIG',   # Cigarettes
    'CIGAR', # Cigars
]

pre2015fixes = prefixes + [
    'SNUF',  # Later grouped
    'CHEW',  # together as SMKLSS
    'INH',   # Inhalants
    'HALL',  # Hallucinogens
    'METH',  # Methamphetamines
    'ANAL',  # Pain relievers
]

pos2015fixes = prefixes + [
    'SMKLSS', # snuff/chew/snus
    'HALLUC', # Hallucinogens
    'INHAL',  # Inhalants
    'METHAM', # Methamphetamines
    'PNRNM',  # Pain relievers
]

post = defaultdict(lambda: 'TRY')
ages = ['MJ', 'ANAL', 'PNRNM', 'INH', 'INHAL',
        'HALL', 'HALLUC', 'METH', 'METHAM']
post.update({key: 'AGE' for key in ages})

mapr = {}
for old, new in zip(ages[1::2], ages[2::2]):
    mapr[new + post[new]] = old + post[old]
    mapr[new + 'REC'] = old + 'REC'

independents = [
    'ALC',   # Alcohol
    'CIG',   # Cigarettes
    'MJ',    # Marijuana
]

dependents = [
    'HALL',  # Hallucinogens
    'METH',  # Methamphetamines
    'ANAL',  # Pain relievers
]

filters = [
    '81', # Age first tried - above this are questionable data
    '4',  # 1: Within 30 days, 2: 30 days < t < 12 mo, 3: > 12 mo
]


# Helper function to spread out each Axis
def square_ax(ax):
    im = ax.get_images()[0]
    ex = im.get_extent()
    ax.set_aspect(abs((ex[1]-ex[0])/(ex[3]-ex[2])))

# Pretty labels for X-axis
xlabs = ['<30days', '>30days', '>12mo']

# Pretty labels for column names
plabels = {
    'HALL': 'Hallucinogens',
    'METH': 'Methamphetamine',
    'ANAL': 'Pain Killers',
     'ALC': 'Alcohol',
     'CIG': 'Cigarettes',
      'MJ': 'Marijuana',
  'CIGTRY': 'Cigarettes',
   'MJAGE': 'Marijuana',
  'ALCTRY': 'Alcohol'
}
