import os
import pandas as pd
from math import pi

def metad(cur_dir, i):
    Path = os.listdir(cur_dir)
    cur_inf = cur_dir + Path[i]
    inf_DF = pd.read_table(cur_inf, sep=",", skipinitialspace=True)
        
    cur_RA = inf_DF.loc[0, 'RA']
    cur_Dec = inf_DF.loc[0, 'Dec']
    cur_centeral_freq_low = float(inf_DF.loc[0, 'central_freq_low_chan'])
    cur_bandwith = float(inf_DF.loc[0, 'total_bandwidth'])


    # central frequency in GHz
    nu = (cur_centeral_freq_low) / 1000
   # bandwith(MHz)
    dnu = cur_bandwith  # 0.3 GHz
   # constant
    constant = pow(pi, 0.5) / 2
    print("central frequency:", nu)
    print("bandwidth", dnu)
    
    return nu, dnu, constant, cur_RA, cur_Dec
