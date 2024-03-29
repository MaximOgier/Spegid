import os
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from pandas import DataFrame, Series
from sklearn.cluster import DBSCAN
from MetaSpeg import *
from sklearn.neighbors import NearestNeighbors
from kneed import KneeLocator
from operator import attrgetter
from sklearn.linear_model import LinearRegression
from scipy.special import erf
from math import log, ceil
import warnings



def SPEGID(cur_dir, i, cur_parent_dir, error_log_fp):
    q = i
    Path = os.listdir(cur_dir)
    path1 = '/data/mogier/Singlepulse_Data/Meta_txt/'
    cur_singlepulses = cur_dir + Path[i]
#    print(cur_singlepulses)
    spe_DF_full = pd.read_table(cur_singlepulses, sep=" ", skipinitialspace=True, skiprows=1, header=None,
                            engine="c", names=["DM", "Sigma", "Time", "Sample", "downfact"],
                            dtype={"DM": np.float64, "Sigma": np.float64, "Time": np.float64,
                                   "Sample": np.uint32, "downfact": np.uint16})
    spe_DF_full = spe_DF_full.sort_values(by=["DM"])
#    print(spe_DF_full)
    spe_DF_full = spe_DF_full.loc[(spe_DF_full['DM'] > 3) & (spe_DF_full['DM'] < 70), ].copy()
#    print(spe_DF_full)
#except EnvironmentError:  # parent of IOError, OSError *and* WindowsError where available
#    error_msg = cur_parent_dir + '/' + cur_dir + ',' + 'reading singlepulses failed!\n'
#    error_log_fp.write(error_msg)
#    exit('reading singlepulses failed!')
    nu, dnu, constant, cur_RA, cur_Dec = metad(path1, i)


##get trial DM values (and the number of DM channels), oberavtion length

# get all DM channels (before removing any single-pulse events with SNR < 5)
    DMs = spe_DF_full.DM.unique()
# get the total number of DM channels
    DM_channel_number = len(DMs)
#    print("DM channel number:", DM_channel_number)

# get observation length in seconds (remove the last 2 seconds, or 7 if 'zerodm' denoising was applied in preprocessing)
    if "zerodm" in cur_dir:
#        print(cur_dir + " zerodm found!")
        t_off = 7
    else:
#        print(cur_dir + " no zerodm!")
        t_off = 0

    obs_length = max(spe_DF_full['Time']) - t_off
# print max(pulses0.time)
#    print("obs_length:", obs_length)

# remove the last few seconds of the observation
    spe_DF_in_range = spe_DF_full.loc[(spe_DF_full['Time'] <= obs_length)]
# print max(pulses0.time)


##double check whether the aggregated singlepulses file was prepocessed correctly

# too many points in file because of RFI, reocord the name of the beam in error log
    if spe_DF_in_range.shape[0] > DM_channel_number * obs_length * 2:
        error_msg = cur_parent_dir + '/' + cur_dir + ',' + 'singlepulses file too large!\n'
        error_log_fp.write(error_msg)
    # exit("singlepulses file too large!")

# check if DM is in asscending order
    if DMs.tolist() != sorted(DMs.tolist()):
        error_msg = cur_parent_dir + '/' + cur_dir + ',' + 'singlepulses file not sorted!\n'
        error_log_fp.write(error_msg)
        exit("singlepulses file not sorted by DM!")



##find out where DM spacing changed

# create a list using the index of DMs
    DM_idx = range(len(DMs))

# create a DM to index ordered dict
    DM_dict = dict(zip(DMs, DM_idx))

# create DM difference list (minimum DM spacing change: 0.01)
    DM_diff = Series(DMs).diff().round(2)
    DM_diff_list = DM_diff.tolist()
    DM_diff_list.append(DM_diff_list[-1])

# pop NAN in the beginning
    DM_diff_list.pop(0)

    DM_diff_final = Series(DM_diff_list)

# record DM spacing for all DM channels in a dict
    DM_diff_dict = dict(zip(DMs, DM_diff_final))

# print DMdiff.head(3)
# print "after append:", len(DMdiff)

# the DataFrame of trial DM values
    DM_DM_diff_DF = DataFrame(DMs, columns=['DMs'])
# add a column of DM difference
    DM_DM_diff_DF['DMdiff'] = DM_diff_final

# get DM spacing values
    DM_DM_diffs = DM_DM_diff_DF.loc[DM_DM_diff_DF['DMdiff'].diff() != 0].copy()
    cur_diffs = DM_DM_diffs['DMdiff'].tolist()

# find out where DM spacing changes
    DM_diff_inflection_idx = DM_DM_diffs.index.values
# the one in the front is the infection point
    DM_inflection_idx = (DM_diff_inflection_idx - 1)[1:]

#    print(DM_inflection_idx)
# DM channel where DM spacing changes
    break_DMs = DMs[DM_inflection_idx]
#    print(break_DMs)

# number of times DM spacing changed
    n_brDMs = len(break_DMs)
#    print(n_brDMs)

# remove SNR < 5 or SNR > 200(including NaN, inf) after getting break_DMs
    spe_DF_clean = spe_DF_in_range.loc[(spe_DF_in_range['Sigma'] < 200) & (spe_DF_in_range['Sigma'] > 5.6)].copy()
    spe_DF_clean['DM_chan_idx'] = spe_DF_clean['DM'].map(DM_dict)
    spe_DF_clean = spe_DF_clean.rename(columns = {'Sample': 'sampling', 'Sigma': 'SNR', 'Time' : 'time'})
#    print(spe_DF_clean)
    
    
    class SinglePulseEventGroup(object):

        __slots__ = ['true_cluster', 'merged', 'grouped',
                     'peak_SNR', 'peak_DM', 'peak_time', 'peak_sampling', 'peak_downfact', 'peak_DM_spacing',
                     'min_DM', 'max_DM', 'min_time', 'max_time',
                     'clipped', 'SNR_sym_index', 'DM_sym_index', 'peak_score', 'size', 'sizeU',
                     'centered_DM', 'center_startDM', 'center_stopDM',
                     'SPEG_rank', 'group_max_SNR', 'group_rank', 'group_median_SNR', 'group_peak_DM',
                     'recur_times', 'bright_recur_times',
                     'n_SPEGs_zero_DM', 'n_brighter_SPEGs_zero_DM',
                     'SPEGs_zero_DM_min_DM', 'brighter_SPEGs_zero_DM_peak_DM', 'brighter_SPEGs_zero_DM_peak_SNR']
    
        def __init__(self, current_list):
            """
            SinglePulseEventGroup constructor.
            :param current_list: a list of attributes of the brightest trial single pulse event within the cluster
            """
            self.true_cluster = True
            self.merged = False
            self.grouped = False
    
            # 5 columns from raw data
            self.peak_DM = current_list[0]
            self.peak_SNR = current_list[1]
            self.peak_time = current_list[2]
            self.peak_sampling = current_list[3]
            self.peak_downfact = current_list[4]
    
            # skip the DM channel index and sampling index
            self.peak_DM_spacing = current_list[7]
            self.min_DM = current_list[8]
            self.max_DM = current_list[9]
            self.min_time = current_list[10]
            self.max_time = current_list[11]
    
            self.clipped = False
            self.SNR_sym_index = -1.0
            self.DM_sym_index = -1.0
            self.peak_score = 0
            self.size = -1
            self.sizeU = -1
    
            self.centered_DM = -1
            self.center_startDM = -1
            self.center_stopDM = -1
    
            self.SPEG_rank = -1
            self.group_max_SNR = 0
            self.group_rank = -1
            self.group_median_SNR = 0
            self.group_peak_DM = -1
    
            self.recur_times = 1
            self.bright_recur_times = 0
    
            self.n_SPEGs_zero_DM = -1
            self.n_brighter_SPEGs_zero_DM = -1
            self.SPEGs_zero_DM_min_DM = -1
            self.brighter_SPEGs_zero_DM_peak_DM = -1
            self.brighter_SPEGs_zero_DM_peak_SNR = -1
    
        def calc_DM_time_thresh(self):
            """
            Calculate the expected DM and time span of an astrophysical pulse (only for bright clusters)
            :return: expected DM and time span as a list
            """
            peak_DM = self.peak_DM
            # print "peakDM:", self.peak_DM
            # print "peak_SNR", self.peak_SNR
            # SNR limit for regular (non-clipped) SPEGs
            SNR_limit = log(self.peak_SNR) / log(2) * 0.4 + 4.5
    
            # SNR = 5 is the base line
            lower_SNR_limit = SNR_limit - 5
            upper_SNR_limit = SNR_limit - 5
    
            cur_cluster_DF = spe_DF_clean.loc[(spe_DF_clean['DM'] >= self.min_DM) & (spe_DF_clean['DM'] <= self.max_DM) &
                                              (spe_DF_clean['time'] >= self.min_time) &
                                              (spe_DF_clean['time'] <= self.max_time), ]
    
            # if there are more than one single-pulse event within the same DM channel, use the brightest one only
            cur_cluster_DF = cur_cluster_DF.groupby('DM', group_keys=False).apply(lambda x: x.loc[x.SNR.idxmax()])
    
            cur_peak_left = cur_cluster_DF.loc[cur_cluster_DF['DM'] < self.peak_DM, ]
            cur_peak_right = cur_cluster_DF.loc[cur_cluster_DF['DM'] > self.peak_DM, ]
            # print curPeakLeft.shape, curPeakRight.shape
    
            # SNR limit for clipped SPEGs, the expected span should be shifted further towards the clipped side,
            # and less on the other side
            if cur_peak_left.shape[0] == 0:
                lower_SNR_limit = lower_SNR_limit - log(self.peak_SNR) / log(2) * 0.05
                upper_SNR_limit = upper_SNR_limit + log(self.peak_SNR) / log(2) * 0.1
    
            elif cur_peak_right.shape[0] == 0:
                lower_SNR_limit = lower_SNR_limit + log(self.peak_SNR) / log(2) * 0.1
                upper_SNR_limit = upper_SNR_limit - log(self.peak_SNR) / log(2) * 0.05
    
            # move 5 times of the DM spacing at the peak to save computation time
            DM_spacing = self.peak_DM_spacing
    
            # sampling time = time / sample
            sampling_time = self.peak_time / self.peak_sampling * 1.0  # of the center
    
            # width (in milliseconds) of the peak single-pulse event (width = sampling time * downfact)
            peak_width = sampling_time * 1000 * self.peak_downfact  # (to milliseconds)
    
            peak_time = self.peak_time
            peak_SNR = self.peak_SNR - 5
    
            # get the DM (upper) bound and time (lower) bound of current SPEG
            upper_idx = 0
    
            while True:
                # check every 5 DM channels
                delta_DM = 5 * DM_spacing * (upper_idx + 1)
                cur_DM = peak_DM + delta_DM
                # calculate expected SNR
                exp_SNR = peak_SNR * constant * ((0.00691 * delta_DM * dnu / (peak_width * nu ** 3)) ** (-1)) * \
                          erf(0.00691 * delta_DM * dnu / (peak_width * nu ** 3))
                upper_idx += 1  # the minimum value is 1
                if exp_SNR < upper_SNR_limit or cur_DM > DMs[-1]:
                    break
    
            upper_DM_bound = cur_DM
            dt_minus = sampling_time * upper_idx * 5
    
            # get the DM (lower) bound and time (upper) bound of current SPEG
            lower_idx = 0  # use this index to calculate time
            while True:
                delta_DM = 5 * DM_spacing * (lower_idx + 1)
                cur_DM = peak_DM - delta_DM
                exp_SNR = peak_SNR * constant * ((0.00691 * delta_DM * dnu / (peak_width * nu ** 3)) ** (-1)) * \
                         erf(0.00691 * delta_DM * dnu / (peak_width * nu ** 3))
                lower_idx += 1
                if exp_SNR < lower_SNR_limit or cur_DM < 0:
                    break
            lower_DM_bound = cur_DM
            dt_plus = sampling_time * lower_idx * 5
    
            upper_time = peak_time + max(peak_width / 2000, dt_plus)
            lower_time = peak_time - max(peak_width / 2000, dt_minus)
    
            DM_time_span = [lower_DM_bound, upper_DM_bound, lower_time, upper_time]
    
            return DM_time_span
    
        def merge(self, other):
            """
            merge clusters with weaker clusters falling into the DM time range
            """
            # print "merging"
            self.min_DM = min(self.min_DM, other.min_DM)
            self.max_DM = max(self.max_DM, other.max_DM)
            self.min_time = min(self.min_time, other.min_time)
            self.max_time = max(self.max_time, other.max_time)
            self.merged = True
            # other is no loner an independent cluster
            other.true_cluster = False
    
        def find_peak_score(self):
            """
            find out whether the cluster is a clipped SPEG , then find out the peak score of the SPEG
            """
            cur_SPEG_DF = spe_DF_clean.loc[(spe_DF_clean['DM'] >= self.min_DM) &
                                              (spe_DF_clean['DM'] <= self.max_DM) &
                                              (spe_DF_clean['time'] >= self.min_time) &
                                              (spe_DF_clean['time'] <= self.max_time), ]
            # group by DM
            cur_SPEG_DF = cur_SPEG_DF.groupby('DM', group_keys=False).apply(lambda x: x.loc[x.SNR.idxmax()])
    
            # # SNR - 5
            # print cur_SPEG_DF.head()
            peak_DM = self.peak_DM
    
            # check clipping or not
            if self.merged:
                # clipped = not any(abs(cur_SPEG_DF['DM'] - DM_centered) <= DMbound)
                lower_DMs = cur_SPEG_DF['DM'][cur_SPEG_DF['DM'] < peak_DM]
                higher_DMs = cur_SPEG_DF['DM'][cur_SPEG_DF['DM'] > peak_DM]
                left_neighbor = (lower_DMs - peak_DM > -6 * self.peak_DM_spacing).any()
                right_neighbor = (higher_DMs - peak_DM < 6 * self.peak_DM_spacing).any()
    
                if not left_neighbor or not right_neighbor:
                    self.clipped = True
    
            # not clipped SPEG
            if not self.clipped:
                if self.peak_SNR > 7:
                    self.centered_DM = self.peak_DM
                    cur_peak_left = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] <= self.peak_DM, ]
                    cur_peak_right = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] >= self.peak_DM, ]
    
                    sum_SNR_left = cur_peak_left['SNR'].sum()
                    sum_SNR_right = cur_peak_right['SNR'].sum()
    
                    cur_sym_SNR = 100
                    if sum_SNR_right > 0:
                        cur_sym_SNR = sum_SNR_left / sum_SNR_right
    
                    DM_range_left = self.peak_DM - float(cur_SPEG_DF['DM'].head(1))
                    DM_range_right = float(cur_SPEG_DF['DM'].tail(1)) - self.peak_DM
    
                    cur_sym_DM = 100
                    if DM_range_right > 0:
                        cur_sym_DM = DM_range_left / DM_range_right
    
                    self.SNR_sym_index = cur_sym_SNR
                    self.DM_sym_index = cur_sym_DM
    
                else:
                    # weak pulses with few points,  # decide the centerDM, find the one with maximum symmetry
                    # within 0.98 of the max SNR
                    cur_SNR_thresh = self.peak_SNR * 0.98
                    peak_candidates = cur_SPEG_DF.loc[(cur_SPEG_DF['SNR']) > cur_SNR_thresh].copy()
                    # print peakCandiates
    
                    # select the top 2
                    if peak_candidates.shape[0] > 1:
                        # ['a', 'b'], ascending=[True, False]
                        peak_candidates.sort_values(by='SNR', ascending=False, inplace=True)
                        peak_candidates = peak_candidates.iloc[:2]
    
                    sym_KVs = []  # store the curCenterDM and symmetry index pair
                    for DMi in peak_candidates['DM']:  # find the one with the largest symmetry
                        cur_peak_left = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] <= DMi, ]
                        cur_peak_right = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] >= DMi, ]
    
                        # changed this to left vs. right instead of min vs max
                        sum_SNR_left = cur_peak_left['SNR'].sum()
                        sum_SNR_right = cur_peak_right['SNR'].sum()
    
                        cur_SNR_sym = 100
                        if sum_SNR_right > 0:
                            cur_SNR_sym = sum_SNR_left / sum_SNR_right
                        # closer to one, means more symmetric
                        cur_SNR_sym_to_one = abs(1 - cur_SNR_sym)
    
                        DM_range_left = DMi - float(cur_SPEG_DF['DM'].head(1))
                        DM_range_right = float(cur_SPEG_DF['DM'].tail(1)) - DMi
    
                        cur_DM_sym = 100
                        if DM_range_right > 0:
                            cur_DM_sym = DM_range_left / DM_range_right
    
                        # sum_SNR_min = min(cur_peak_left['SNR'].sum(), cur_peak_right['SNR'].sum())
                        # sum_SNR_max = max(cur_peak_left['SNR'].sum(), cur_peak_right['SNR'].sum())
    
                        # cur_SNR_sym = sum_SNR_min / sum_SNR_max
    
                        # DM_range1 = DMi - float(cur_SPEG_DF['DM'].head(1))
                        # DM_range2 = float(cur_SPEG_DF['DM'].tail(1)) - DMi
                        # cur_DM_sym = min(DM_range1, DM_range2) / max(DM_range1, DM_range2)
    
                        sym_KVs.append([DMi, cur_SNR_sym, cur_DM_sym, cur_SNR_sym_to_one])
    
                    # convert to data frame
                    sym_KVs_DF = DataFrame(sym_KVs)
                    sym_KVs_DF.columns = ['DM', 'SNR_sym', 'DM_sym', 'SNR_sym_to_one']
    
                    # sort by SNR_sym close to 1
                    cur_peak_row = sym_KVs_DF.loc[sym_KVs_DF.SNR_sym_to_one.idxmin()]
    
                    cur_center_DM = cur_peak_row[0]
                    cur_SNR_sym = cur_peak_row[1]
                    cur_DM_sym = cur_peak_row[2]
    
                    # print curCenterDM, curSymIndex
                    self.centered_DM = cur_center_DM
                    self.SNR_sym_index = cur_SNR_sym
                    self.DM_sym_index = cur_DM_sym
    
            else:  # clipped SPEG
                cur_peak_left = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] < self.peak_DM, ]
                cur_peak_right = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] > self.peak_DM, ]
    
                sum_SNR_left = cur_peak_left['SNR'].sum()
                sum_SNR_right = cur_peak_right['SNR'].sum()
    
                cur_SNR_sym = 100
                if sum_SNR_right > 0:
                    cur_SNR_sym = sum_SNR_left / sum_SNR_right
    
                self.SNR_sym_index = cur_SNR_sym
    
            df1 = None
            df2 = None
            df3 = None
            df4 = None
            df5 = None
            df6 = None
    
            if not self.clipped:  # not clipped SPEG
                # if self.SNR_sym_index > 0.25 and self.DM_sym_index > 0.2:  # tunable
                if 4.0 > self.SNR_sym_index > 0.25 and 5.0 > self.DM_sym_index > 0.2:  # tunable
                    cur_peak_left = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] <= self.centered_DM, ]
                    cur_peak_right = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] >= self.centered_DM, ]
    
                    # find central part and divide into left and right
                    cur_central_DMs_left = cur_peak_left.loc[cur_SPEG_DF['SNR'] >= self.peak_SNR * 0.9, 'DM']
    
                    if cur_central_DMs_left.size > 0:
                        # print cur_central_DMs_left
                        cur_DM_left_temp = cur_central_DMs_left.tolist()[0]
                    else:  # no points between 90% and 100%
                        cur_side_DMs_left = cur_peak_left.loc[cur_SPEG_DF['SNR'] < self.peak_SNR * 0.9, 'DM']
                        # print cur_side_DMs_left.shape
                        # print cur_side_DMs_left
                        cur_DM_left_temp = cur_side_DMs_left.tolist()[-1]
    
                    # when DM spacing is small
                    if self.peak_DM_spacing <= 0.5:
                        # really wide peaks
                        if self.centered_DM - cur_DM_left_temp >= 6:
                            self.center_startDM = self.centered_DM - 6
                        # moderately wide peaks
                        elif self.centered_DM - cur_DM_left_temp >= 1:
                            self.center_startDM = cur_DM_left_temp
                        # relatively narrow peaks
                        elif self.centered_DM - self.min_DM >= 1:
                            self.center_startDM = self.centered_DM - 1
                        # narrow peaks
                        else:
                            self.center_startDM = self.min_DM
                    # when DM spacing is moderately large
                    elif self.peak_DM_spacing < 3:
                        # really wide peaks
                        if self.centered_DM - cur_DM_left_temp >= 6:
                            self.center_startDM = self.centered_DM - 6
                        # moderately wide peaks
                        elif self.centered_DM - cur_DM_left_temp >= 2 * self.peak_DM_spacing:
                            self.center_startDM = cur_DM_left_temp
                        # relatively narrow peaks
                        elif self.centered_DM - self.min_DM > 2 * self.peak_DM_spacing:
                            self.center_startDM = self.centered_DM - 2 * self.peak_DM_spacing
                        # narrow peaks
                        else:
                            self.center_startDM = self.min_DM
                    # when DM spacing is large
                    else:
                        # really wide peaks
                        if self.centered_DM - cur_DM_left_temp >= 2 * self.peak_DM_spacing:
                            self.center_startDM = self.centered_DM - 2 * self.peak_DM_spacing
                        # relatively narrow peaks
                        elif self.centered_DM - self.min_DM >= 2 * self.peak_DM_spacing:
                            self.center_startDM = self.centered_DM - 2 * self.peak_DM_spacing
                        # narrow peaks
                        else:
                            self.center_startDM = self.min_DM
    
                    # the right part
                    cur_central_DMs_right = cur_peak_right.loc[cur_SPEG_DF['SNR'] >= self.peak_SNR * 0.9, 'DM']
    
                    if cur_central_DMs_right.size > 0:
                        # print cur_central_DMs_right
                        cur_DM_right_temp = cur_central_DMs_right.tolist()[-1]
                        # print cur_DM_right_temp
                    else:  # no points between 100% and 90%
                        cur_side_DMs_right = cur_peak_right.loc[cur_SPEG_DF['SNR'] < self.peak_SNR * 0.9, 'DM']
                        cur_DM_right_temp = cur_side_DMs_right.tolist()[0]
    
                    # when DM spacing is small
                    if self.peak_DM_spacing <= 0.5:
                        # really wide peaks
                        if cur_DM_right_temp - self.centered_DM >= 6:
                            self.center_stopDM = self.centered_DM + 6
                        # moderately wide peaks
                        elif cur_DM_right_temp - self.centered_DM >= 1:
                            self.center_stopDM = cur_DM_right_temp
                        # relatively narrow peaks
                        elif self.max_DM - self.centered_DM >= 1:
                            self.center_stopDM = self.centered_DM + 1
                        # narrow peaks
                        else:
                            self.center_stopDM = self.max_DM
                    # when DM spacing is moderately large
                    elif self.peak_DM_spacing < 3:
                        # really wide peaks
                        if cur_DM_right_temp - self.centered_DM >= 6:
                            self.center_stopDM = self.centered_DM + 6
                        # moderately wide peaks
                        elif cur_DM_right_temp - self.centered_DM >= 2 * self.peak_DM_spacing:
                            self.center_stopDM = cur_DM_left_temp
                        # relatively narrow peaks
                        elif self.max_DM - self.centered_DM >= 2 * self.peak_DM_spacing:
                            self.center_stopDM = self.centered_DM + 2 * self.peak_DM_spacing
                        # narrow peaks
                        else:
                            self.center_stopDM = self.max_DM
                    # when DM spacing is large
                    else:
                        # really wide peaks
                        if cur_DM_right_temp - self.centered_DM >= 2 * self.peak_DM_spacing:
                            self.center_stopDM = self.centered_DM + 2 * self.peak_DM_spacing
                        # relatively narrow peaks
                        elif self.max_DM - self.centered_DM >= 2 * self.peak_DM_spacing:
                            self.center_stopDM = self.centered_DM + 2 * self.peak_DM_spacing
                        # narrow peaks
                        else:
                            self.center_stopDM = self.max_DM
    
                    # check if both sides have more than 3 points, at least 7 points in total
                    if cur_peak_left.shape[0] > 3 and cur_peak_right.shape[0] > 3:
                        # at least 4 points on each side, 7 points in total
                        left_DM_range = self.centered_DM - float(cur_peak_left['DM'].head(1))  # head is the minimum
                        right_DM_range = float(cur_peak_right['DM'].tail(1)) - self.centered_DM  # tail is the maximum
                        left_DM_step = left_DM_range / 3
                        right_DM_step = right_DM_range / 3
                        if right_DM_step > left_DM_step:
                            right_DM_step = min(right_DM_step, 2 * left_DM_step)
                        else:
                            left_DM_step = min(left_DM_step, 2 * right_DM_step)
    
                        DM1 = self.centered_DM - left_DM_step
                        DM2 = self.centered_DM - 2 * left_DM_step
                        DM3 = self.centered_DM + right_DM_step
                        DM4 = self.centered_DM + 2 * right_DM_step
    
                        df1 = cur_peak_left.loc[cur_peak_left['DM'] >= DM1, ]
                        # check df1: if there are at least 1 point between DM1 and center DM
                        if df1.shape[0] > 1:
                            # check df2
                            df2 = cur_peak_left.loc[(cur_peak_left['DM'] >= DM2) & (cur_peak_left['DM'] <= DM1), ]
                            if df2.shape[0] > 1:
                                # if there are at least 2 points between DM2 and DM1
                                df3 = cur_peak_left.loc[(cur_peak_left['DM'] <= DM2), ]
                                # if there are less than 2 points below DM2
                                if df3.shape[0] < 2:
                                    df3 = cur_peak_left.loc[(cur_peak_left['DM'] <= DM1), ]
                                    # df3 is a super set of df2, which has at least 2 points
                            else:
                                # if there are less than 2 points between DM2 and DM1
                                df2 = cur_peak_left.loc[(cur_peak_left['DM'] >= DM2), ]
                                # df2 is a super set of df1, which has at least 2 points
                                df3 = cur_peak_left.loc[(cur_peak_left['DM'] <= DM2), ]
                                # if there are less than 2 points below DM2
                                if df3.shape[0] < 2:
                                    df3 = cur_peak_left.loc[(cur_peak_left['DM'] <= DM1), ]
                                    # if there are less than 2 points below DM1
                                    if df3.shape[0] < 2:
                                        df3 = cur_peak_left
                                        # df3 is a super set of df1, which has at least 2 points
                        else:  # if there is not any point between DM1 and center DM
                            df1 = cur_peak_left.loc[(cur_peak_left['DM'] >= DM2), ]
                            # if there is at least 1 point between DM2 and DM1
                            if df1.shape[0] > 1:
                                df2 = cur_peak_left.loc[(cur_peak_left['DM'] >= DM2) & (cur_peak_left['DM'] <= DM1), ]
                                # if there are at least 2 points between DM2 and DM1
                                if df2.shape[0] > 1:
                                    df3 = cur_peak_left.loc[(cur_peak_left['DM'] <= DM2), ]
                                    # if there are less than 2 points below DM2
                                    if df3.shape[0] < 2:
                                        df3 = cur_peak_left.loc[(cur_peak_left['DM'] <= DM1), ]
                                        # df3 is a super set of df2, which has at least 2 points
                                else:  # there is 1 and only 1 point between DM2 and DM1
                                    df2 = df1
                                    df3 = cur_peak_left.loc[(cur_peak_left['DM'] <= DM2), ]
                                    # if there are less than 2 points below DM2
                                    if df3.shape[0] < 2:
                                        # if there is 1 point below DM2
                                        df3 = cur_peak_left.loc[(cur_peak_left['DM'] <= DM1), ]
                        # right side
                        df4 = cur_peak_right.loc[cur_peak_right['DM'] <= DM3,]
                        # check df4: if there are at least 2 points between center and DM3
                        if df4.shape[0] > 1:
                            # check df5: if there are at least 2 points between DM3 and DM4
                            df5 = cur_peak_right.loc[(cur_peak_right['DM'] >= DM3) & (cur_peak_right['DM'] <= DM4), ]
                            # if there are at least 2 points between DM3 and DM4
                            if df5.shape[0] > 1:
                                # if there are at least 2 points above DM4
                                df6 = cur_peak_right.loc[(cur_peak_right['DM'] >= DM4), ]
                                # if there are less than 2 points above DM4
                                if df6.shape[0] < 2:
                                    df6 = cur_peak_right.loc[(cur_peak_right['DM'] >= DM3), ]
                                    # df6 is a super set of df5, which has more than 2 points
                                    # if there are at less than 2 points between DM3 and DM4
                            else:
                                df5 = cur_peak_right.loc[(cur_peak_right['DM'] <= DM4), ]
                                # df5 is a super set of df4, which has at least 2 points
                                df6 = cur_peak_right.loc[(cur_peak_right['DM'] >= DM4), ]
                                # if there are less than 2 points above DM4
                                if df6.shape[0] < 2:
                                    df6 = cur_peak_right.loc[(cur_peak_right['DM'] >= DM3), ]
                                    # if there are at less than 2 points above DM3
                                    if df6.shape[0] < 2:
                                        df6 = cur_peak_right
                        else:  # if there is not any point between center and DM3
                            df4 = cur_peak_right.loc[(cur_peak_right['DM'] <= DM4), ]
                            if df4.shape[0] > 1:
                                # at least 1 point between DM3 and DM4
                                df5 = cur_peak_right.loc[(cur_peak_right['DM'] >= DM3) & (cur_peak_right['DM'] <= DM4), ]
                                if df5.shape[0] > 1:
                                    # at least 2 points between DM3 and DM4
                                    df6 = cur_peak_right.loc[(cur_peak_right['DM'] >= DM4), ]
                                    if df6.shape[0] < 2:
                                        # if there is only 1 point above DM4
                                        df6 = cur_peak_right.loc[(cur_peak_right['DM'] >= DM3), ]
                                        # df6 is a super set of df5, which has at least 2 points
                                else:  # exactly 1 point between DM3 and DM4
                                    df5 = df4
                                    df6 = cur_peak_right.loc[(cur_peak_right['DM'] >= DM4), ]
                                    # only one point above DM4
                                    if df6.shape[0] < 2:
                                        df6 = cur_peak_right.loc[(cur_peak_right['DM'] >= DM3), ]
                    elif cur_peak_left.shape[0] > 2 and cur_peak_right.shape[0] > 2:
                        # on one side there's at most 3 points, in total 5 points or more
                        if 2.041 > self.DM_sym_index > 0.49:
                            if cur_peak_left.shape[0] > 3:  # divide into 2 parts
                                nrow_left = cur_peak_left.shape[0]  # number of rows in left peak
                                nrowDF = cur_peak_left.shape[0] // 2  # number of rows in a df
    
                                df1 = cur_peak_left.iloc[(nrow_left - nrowDF):]
                                df2 = cur_peak_left.iloc[: (nrow_left - nrowDF)]
                            else:  # equals to 3
                                df1 = cur_peak_left.iloc[1:]
                                df2 = cur_peak_left.iloc[0:2]
                                # df3 = cur_peak_left
    
                            if cur_peak_right.shape[0] > 3:  # divide into 2 parts
                                # nrow_right = cur_peak_right.shape[0]
                                nrowDF = cur_peak_right.shape[0] // 2  # number of rows in a df
                                df4 = cur_peak_right.iloc[: nrowDF]
                                df5 = cur_peak_right.iloc[nrowDF:]
                                # df6 = cur_peak_right.iloc[(2 * nrowDF):]
                            else:
                                df4 = cur_peak_right.iloc[0:2]
                                df5 = cur_peak_right.iloc[1:]
                                # df6 = cur_peak_right
    
            else:  # clipped SPEG
                # min side greater than 3
                if 10.0 > self.SNR_sym_index > 0.1:
                    # print self.peak_DM
                    cur_peak_left = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] < self.peak_DM,]
                    cur_peak_right = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] > self.peak_DM,]
                    if cur_peak_left.shape[0] > 3 and cur_peak_right.shape[0] > 3:
                        # at least 4 points on each side, 9 points in total
                        left_DM_range = float(cur_peak_left['DM'].tail(1)) - float(cur_peak_left['DM'].head(1))
                        # head is the minimum
                        right_DM_range = float(cur_peak_right['DM'].tail(1)) - float(cur_peak_right['DM'].head(1))
                        # tail is the maximum
    
                        left_DM_step = left_DM_range // 2
                        right_DM_step = right_DM_range // 2
    
                        if right_DM_step > left_DM_step:
                            right_DM_step = min(right_DM_step, 2 * left_DM_step)
                        else:
                            left_DM_step = min(left_DM_step, 2 * right_DM_step)
    
                        DM1 = float(cur_peak_left['DM'].tail(1)) - left_DM_step
                        DM3 = float(cur_peak_right['DM'].head(1)) + right_DM_step
    
                        df1 = cur_peak_left.loc[(cur_peak_left['DM'] >= DM1), ]
                        # check df1: if there are at least 2 point between DM1 and center DM
                        if df1.shape[0] > 1:
                            # check df2
                            df2 = cur_peak_left.loc[(cur_peak_left['DM'] <= DM1), ]
                            # if there are at least 2 points between DM2 and DM1
                            if df2.shape[0] < 2:
                                df2 = None
    
                        # right side
                        df4 = cur_peak_right.loc[cur_peak_right['DM'] <= DM3, ]
                        # check df4: if there are at least 2 points between center and DM3
                        if df4.shape[0] > 1:
                            # check df5: if there are at least 2 points between DM3 and DM4
                            df5 = cur_peak_right.loc[(cur_peak_right['DM'] >= DM3), ]
                            # if there are at least 2 points between DM3 and DM4
                            if df5.shape[0] < 2:
                                df5 = None
    
                        # select the central part
                        df_left = cur_peak_left.tail(cur_peak_left.shape[0] // 2)
                        df_right = cur_peak_right.head(cur_peak_right.shape[0] // 2)
    
                        # use 4.999 instead of 5 to avoid 0 weights
                        model_left = LinearRegression().fit(X=df_left['DM'].values.reshape(-1, 1), y=df_left['SNR'],
                                                            sample_weight=(df_left['SNR'] - 4.999))
    
                        model_right = LinearRegression().fit(X=df_right['DM'].values.reshape(-1, 1), y=df_right['SNR'],
                                                             sample_weight=(df_right['SNR'] - 4.999))
    
                        cur_DM_min = float(df_left['DM'].tail(1))
                        cur_DM_max = float(df_right['DM'].head(1))
                        cur_DM_min_idx = DM_dict.get(cur_DM_min)
                        cur_DM_max_idx = DM_dict.get(cur_DM_max)
                        cur_DMs = DMs[cur_DM_min_idx:cur_DM_max_idx]
    
                        intercept_left = model_left.intercept_
                        slope_left = model_left.coef_[0]
    
                        intercept_right = model_right.intercept_
                        slope_right = model_right.coef_[0]
    
                        fitted_left = cur_DMs * slope_left + intercept_left
                        fitted_right = cur_DMs * slope_right + intercept_right
    
                        fitted_diff = abs(fitted_left - fitted_right)
                        min_diff = min(fitted_diff)
                        # print self.centered_DM
                        self.centered_DM = cur_DMs[fitted_diff == min_diff][0]
    
                        # re-divide the cluster
                        cur_peak_left2 = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] < self.centered_DM, ]
                        cur_peak_right2 = cur_SPEG_DF.loc[cur_SPEG_DF['DM'] > self.centered_DM, ]
    
                        left_DM_range2 = self.centered_DM - float(cur_peak_left2['DM'].head(1))  # head is the minimum
                        right_DM_range2 = float(cur_peak_right2['DM'].tail(1)) - self.centered_DM  # tail is the maximum
    
                        cur_DM_sym = 100
                        if right_DM_range2 > 0:
                            cur_DM_sym = left_DM_range2 / right_DM_range2
    
                        self.DM_sym_index = cur_DM_sym
    
                        # find central part, devide into left and right
                        cur_central_DMs_left = cur_peak_left.loc[cur_SPEG_DF['SNR'] >= self.peak_SNR * 0.9, 'DM']
    
                        if cur_central_DMs_left.size > 0:
                            cur_DM_left_temp = cur_central_DMs_left.tolist()[0]
                        else:  # no points between 90% and 100%
                            cur_side_DMs_left = cur_peak_left.loc[cur_SPEG_DF['SNR'] < self.peak_SNR * 0.9, 'DM']
                            cur_DM_left_temp = cur_side_DMs_left.tolist()[-1]
    
                        # when DM spacing is small
                        if self.peak_DM_spacing <= 0.5:
                            # really wide peaks
                            if self.centered_DM - cur_DM_left_temp >= 6 * 2:
                                self.center_startDM = self.centered_DM - 6 * 2
                            # moderately wide peaks
                            elif self.centered_DM - cur_DM_left_temp >= 2 * 2:
                                self.center_startDM = cur_DM_left_temp
                            # relatively narrow peaks
                            elif self.centered_DM - self.min_DM >= 2 * 2:
                                self.center_startDM = self.centered_DM - 2 * 2
                            # narrow peaks
                            else:
                                self.center_startDM = self.min_DM
                        # when DM spacing is moderately large
                        elif self.peak_DM_spacing < 3:
                            # really wide peaks
                            if self.centered_DM - cur_DM_left_temp >= 6 * 2:
                                self.center_startDM = self.centered_DM - 6 * 2
                            # moderately wide peaks
                            elif self.centered_DM - cur_DM_left_temp >= 2 * self.peak_DM_spacing * 2:
                                self.center_startDM = cur_DM_left_temp
                            # relatively narrow peaks
                            elif self.centered_DM - self.min_DM > 2 * self.peak_DM_spacing * 2:
                                self.center_startDM = self.centered_DM - 2 * self.peak_DM_spacing * 2
                            # narrow peaks
                            else:
                                self.center_startDM = self.min_DM
                        # when DM spacing is large
                        else:
                            # really wide peaks
                            if self.centered_DM - cur_DM_left_temp >= 2 * self.peak_DM_spacing * 2:
                                self.center_startDM = self.centered_DM - 2 * self.peak_DM_spacing * 2
                            # relatively narrow peaks
                            elif self.centered_DM - self.min_DM >= 2 * self.peak_DM_spacing * 2:
                                self.center_startDM = self.centered_DM - 2 * self.peak_DM_spacing * 2
                            # narrow peaks
                            else:
                                self.center_startDM = self.min_DM
    
                        # the right part
                        cur_central_DMs_right = cur_peak_right.loc[cur_SPEG_DF['SNR'] >= self.peak_SNR * 0.9, 'DM']
    
                        if cur_central_DMs_right.size > 0:
                            # print cur_central_DMs_right
                            cur_DM_right_temp = cur_central_DMs_right.tolist()[-1]
                            # print cur_DM_right_temp
                        else:  # no points between 100% and 90%
                            cur_side_DMs_right = cur_peak_right.loc[cur_SPEG_DF['SNR'] < self.peak_SNR * 0.9, 'DM']
                            cur_DM_right_temp = cur_side_DMs_right.tolist()[0]
    
                        # when DM spacing is small
                        if self.peak_DM_spacing <= 0.5:
                            # really wide peaks
                            if cur_DM_right_temp - self.centered_DM >= 6 * 2:
                                self.center_stopDM = self.centered_DM + 6 * 2
                            # moderately wide peaks
                            elif cur_DM_right_temp - self.centered_DM >= 2 * 2:
                                self.center_stopDM = cur_DM_right_temp
                            # relatively narrow peaks
                            elif self.max_DM - self.centered_DM >= 2 * 2:
                                self.center_stopDM = self.centered_DM + 2 * 2
                            # narrow peaks
                            else:
                                self.center_stopDM = self.max_DM
                        # when DM spacing is moderately large
                        elif self.peak_DM_spacing < 3:
                            # really wide peaks
                            if cur_DM_right_temp - self.centered_DM >= 6 * 2:
                                self.center_stopDM = self.centered_DM + 6 * 2
                            # moderately wide peaks
                            elif cur_DM_right_temp - self.centered_DM >= 2 * self.peak_DM_spacing * 2:
                                self.center_stopDM = cur_DM_left_temp
                            # relatively narrow peaks
                            elif self.max_DM - self.centered_DM >= 2 * self.peak_DM_spacing * 2:
                                self.center_stopDM = self.centered_DM + 2 * self.peak_DM_spacing * 2
                            # narrow peaks
                            else:
                                self.center_stopDM = self.max_DM
                        # when DM spacing is large
                        else:
                            # really wide peaks
                            if cur_DM_right_temp - self.centered_DM >= 2 * self.peak_DM_spacing * 2:
                                self.center_stopDM = self.centered_DM + 2 * self.peak_DM_spacing * 2
                            # relatively narrow peaks
                            elif self.max_DM - self.centered_DM >= 2 * self.peak_DM_spacing * 2:
                                self.center_stopDM = self.centered_DM + 2 * self.peak_DM_spacing * 2
                            # narrow peaks
                            else:
                                self.center_stopDM = self.max_DM
    
            if (df1 is not None) and (df2 is not None) and (df3 is not None) and (df4 is not None) and \
                    (df5 is not None) and (df6 is not None):
                model1 = LinearRegression().fit(X=df1['DM'].values.reshape(-1, 1), y=df1['SNR'],
                                                sample_weight=df1['SNR'] - 4.999)
    
                model2 = LinearRegression().fit(X=df2['DM'].values.reshape(-1, 1), y=df2['SNR'],
                                                sample_weight=df2['SNR'] - 4.999)
    
                model3 = LinearRegression().fit(X=df3['DM'].values.reshape(-1, 1), y=df3['SNR'],
                                                sample_weight=df3['SNR'] - 4.999)
    
                model4 = LinearRegression().fit(X=df4['DM'].values.reshape(-1, 1), y=df4['SNR'],
                                                sample_weight=df4['SNR'] - 4.999)
    
                model5 = LinearRegression().fit(X=df5['DM'].values.reshape(-1, 1), y=df5['SNR'],
                                                sample_weight=df5['SNR'] - 4.999)
    
                model6 = LinearRegression().fit(X=df6['DM'].values.reshape(-1, 1), y=df6['SNR'],
                                                sample_weight=df6['SNR'] - 4.999)
    
                slope1 = model1.coef_[0]
                slope2 = model2.coef_[0]
                slope3 = model3.coef_[0]
                slope4 = model4.coef_[0]
                slope5 = model5.coef_[0]
                slope6 = model6.coef_[0]
    
                slope_set = [slope3, slope2, slope1, slope4, slope5, slope6]
    
                slope_bound = max(0.01 / self.peak_DM_spacing, 0.01)
    
                def slope_code(x):
                    if x > slope_bound:
                        return 1
                    elif x < -slope_bound:
                        return -1
                    else:
                        return 0
    
                slope_set_coded = list(map(slope_code, slope_set))
                # make sure it's not all flat
                self.peak_score = sum(slope_set_coded[0:3]) - sum(slope_set_coded[3:6])
            elif (df1 is not None) and (df2 is not None) and (df4 is not None) and (df5 is not None):
    
                model1 = LinearRegression().fit(X=df1['DM'].values.reshape(-1, 1), y=df1['SNR'],
                                                sample_weight=df1['SNR'] - 4.999)
    
                model2 = LinearRegression().fit(X=df2['DM'].values.reshape(-1, 1), y=df2['SNR'],
                                                sample_weight=df2['SNR'] - 4.999)
    
                model4 = LinearRegression().fit(X=df4['DM'].values.reshape(-1, 1), y=df4['SNR'],
                                                sample_weight=df4['SNR'] - 4.999)
    
                model5 = LinearRegression().fit(X=df5['DM'].values.reshape(-1, 1), y=df5['SNR'],
                                                sample_weight=df5['SNR'] - 4.999)
    
                slope1 = model1.coef_[0]
                slope2 = model2.coef_[0]
    
                slope4 = model4.coef_[0]
                slope5 = model5.coef_[0]
    
                slope_set = [slope2, slope1, slope4, slope5]
                slope_bound = max(0.01 / self.peak_DM_spacing, 0.01)
    
                def slope_code(x):
                    if x > slope_bound:
                        return 1
                    elif x < -slope_bound:
                        return -1
                    else:
                        return 0
    
                slope_set_coded = list(map(slope_code, slope_set))
                # make sure it's not all flat
                self.peak_score = sum(slope_set_coded[0:2]) - sum(slope_set_coded[2:4])
    
        def calc_zero_DM_extent(self):
            cur_DM_time_extent = list()
    
            # peak_sampling is time index
            cur_peak_sampling = self.peak_sampling
    
            cur_peak_time = self.peak_time
            cur_peak_DM = self.peak_DM
    
            cur_samplingtime = cur_peak_time / cur_peak_sampling * 1.0
    
            # width (in milliseconds) of the peak single-pulse event (width = sampling time * downfact)
            cur_peak_width = cur_samplingtime * self.peak_downfact  # (in seconds)
    
            cur_peak_DM_spacing = cur_SPEG.peak_DM_spacing
    
            # equivalent number of DM channels with such DM spacing till 0
            n_channel_equi = ceil(cur_peak_DM / cur_peak_DM_spacing)
    
            # upper_time_extent
            upper_time_extent = cur_peak_time + n_channel_equi * cur_samplingtime + cur_peak_width / 2
    
            # min DM
            cur_DM_time_extent.append(-1.0)
            # max DM
            cur_DM_time_extent.append(cur_peak_DM)
            # min time
            cur_DM_time_extent.append(cur_peak_time)
            # max time
            cur_DM_time_extent.append(upper_time_extent)
    
            return cur_DM_time_extent
    
        def __str__(self):
            # print cur_cluster
            s = ["\n\tCluster rank:   %5d" % self.SPEG_rank,
                 "\tgroup rank:   %5d" % self.group_rank,
                 "\tsize:   %5d" % self.size,
                 "\tpeak_score:   %5d" % self.peak_score,
                 "\trecurrence times:   %5d" % self.recur_times,
                 "\tstart center DM:   %5.2f" % self.center_startDM,
                 "\tstop center DM:   %5.2f" % self.center_stopDM,
                 "\tpeak_DM_spacing:   %5.2f" % self.peak_DM_spacing,
                 "\tpeak DM:   %5.2f" % self.peak_DM,
                 "\tpeak time: %3.6f" % self.peak_time,
                 "\tpeak SNR:  %3.2f" % self.peak_SNR,
                 "\tpeak sampling:   %d" % self.peak_sampling,
                 "\tpeak_downfact: %d" % self.peak_downfact,
                 "\tmin DM:   %5.2f" % self.min_DM,
                 "\tmax DM: %5.2f" % self.max_DM,
                 "\tmin time:  %3.6f" % self.min_time,
                 "\tmax time:   %3.6f" % self.max_time,
                 "\ttrue cluster:  %s" % self.true_cluster,
                 "\tclipped:  %s" % self.clipped,
                 "\tmerged:  %s" % self.merged,
                 "\tcentered_DM:  %s" % self.centered_DM,
                 "\tDM_sym_index: %5.5f" % self.DM_sym_index,
                 "\tSNR_sym_index: %5.5f" % self.SNR_sym_index,
                 "--------------------------------"
                 ]
            return '\n'.join(s)
        
    all_clusters = []
    border_clusters = []
    cur_minPts = 5
    lab = np.array([])
    df = pd.DataFrame({"DM":[], "DM_chan_idx":[], "sampling":[], "SNR":[], "time":[], "downfact":[], "sampling_idx":[]})
# divide into n_brDMs+1 sections
    print(n_brDMs)
#    print(break_DMs)
#    print(cur_diffs)

#kneelocator for all data
#I add this part for cutt k-nearest-neightbour for DBSCAN if number of point are not enought 
    def knee_all(cur_minPts, spe_DF_clean):
        c = cur_minPts-1
        cur_DF = spe_DF_clean.loc[(spe_DF_clean['DM'] > 3) & (spe_DF_clean['DM'] < 70), ].copy()
        if cur_DF.shape[0] > cur_minPts:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cur_last_row = cur_DF.tail(1)
#            print(cur_last_row)
            cur_samplingtime = float(cur_last_row['time'] / cur_last_row['SNR'])
            
#            print(cur_samplingtime)
# convert time to time index to the change in DM channel index
            if float(cur_samplingtime) == 0:
                cur_DF['sampling_idx'] = 0.01
            else :
                cur_DF['sampling_idx'] = cur_DF['time'] / cur_samplingtime
        print(cur_DF)
        nbrs = NearestNeighbors(n_neighbors = c, n_jobs = 1).fit(cur_DF[['sampling_idx', 'DM_chan_idx']])
        n_dist , n_ind = nbrs.kneighbors(cur_DF[['sampling_idx', 'DM_chan_idx']])
        sort_n_dist = np.sort(n_dist, axis = 0)
        k_dist = sort_n_dist[:, c-1]            
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            kneedle = KneeLocator(x = range(1, len(n_dist)+1), y = k_dist, S = 1.0, curve = "concave", direction = "increasing", online = True)
        return  kneedle.knee_y
    r = knee_all(cur_minPts, spe_DF_clean)
#    print(r)
    
    for i in range(n_brDMs + 1):
        cur_minPts = 5
        if 0 < i < n_brDMs:
            DM_upper_border = break_DMs[i]
            DM_upper_limit = DM_upper_border - cur_minPts * cur_diffs[i]
            DM_lower_border = break_DMs[i - 1]
            DM_lower_limit = DM_lower_border - cur_minPts * cur_diffs[i - 1]
        elif i == 0:  # no lower limit
            DM_upper_border = break_DMs[i]
            DM_upper_limit = DM_upper_border - cur_minPts * cur_diffs[i]
            DM_lower_border = 3 
            DM_lower_limit = DM_lower_border
        else:
            DM_upper_border = 70
            DM_upper_limit = DM_upper_border
            DM_lower_border = break_DMs[i - 1]
            DM_lower_limit = DM_lower_border - cur_minPts * cur_diffs[i - 1]

        cur_DF = spe_DF_clean.loc[(spe_DF_clean['DM'] > DM_lower_limit) & (spe_DF_clean['DM'] < DM_upper_border), ].copy()
        cur_DF = cur_DF.loc[(cur_DF['time'] > 0.1), ].copy()
#        print(cur_DF)
#        print(spe_DF_clean)
        if cur_DF.shape[0] > cur_minPts:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cur_last_row = cur_DF.tail(1)
#            print(cur_last_row)
            cur_samplingtime = float(cur_last_row['time'] / cur_last_row['SNR'])
            
#            print(cur_samplingtime)
        # convert time to time index to the change in DM channel index
            if float(cur_samplingtime) == 0:
                cur_DF['sampling_idx'] = 0.01
            else :
                cur_DF['sampling_idx'] = cur_DF['time'] / cur_samplingtime
#            print(cur_DF)
        # use DM and time index in DBSCAN clustering
            c = cur_minPts-1
#            print(cur_DF)
#use KNN algorithm for minum distance between points
            nbrs = NearestNeighbors(n_neighbors = c, n_jobs = 1).fit(cur_DF[['sampling_idx', 'DM_chan_idx']])
            n_dist , n_ind = nbrs.kneighbors(cur_DF[['sampling_idx', 'DM_chan_idx']])
            sort_n_dist = np.sort(n_dist, axis = 0)
            k_dist = sort_n_dist[:, c-1]            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                kneedle = KneeLocator(x = range(1, len(n_dist)+1), y = k_dist, S = 1.0, curve = "concave", direction = "increasing", online = True)
#            print(kneedle.knee_y)
            if kneedle.knee_y == None:
                h = r
            elif kneedle.knee_y > 50:
                h = r
            else:
                h = kneedle.knee_y
#            print(h)
#            n_jobs = 4
#            print(h)
            db = DBSCAN(eps=h , min_samples=cur_minPts, n_jobs = 1).fit(cur_DF[['sampling_idx', 'DM_chan_idx']])
#            print(db)
            labels = db.labels_
            unique_labels = set(labels)
            lab = np.concatenate((lab,labels), axis= None)
#            print(cur_DF)
            frame = [df , cur_DF]
            df= pd.concat(frame, sort=True)
#            print(df)
        # noise
            unique_labels.discard(-1)
#            print(len(unique_labels))
            for k in unique_labels:
                class_member_mask = (labels == k)
                cur_cluster_DF = cur_DF[class_member_mask]
                # get the brightest event of the current cluster, as well as the DM and time range
                peak_row = cur_cluster_DF.loc[cur_cluster_DF.SNR.idxmax()]
                cur_peak_DM = peak_row['DM']
                
                cur_peak_DM_spacing = DM_diff_dict.get(cur_peak_DM)
                cur_list = peak_row.tolist()
                cur_min_DM = float(cur_cluster_DF['DM'].head(1))
                cur_max_DM = float(cur_cluster_DF['DM'].tail(1))
                cur_min_time = min(cur_cluster_DF['time'])
                cur_max_time = max(cur_cluster_DF['time'])
                
                cur_list.extend([cur_peak_DM_spacing, cur_min_DM, cur_max_DM, cur_min_time, cur_max_time])

                # generate the cluster
#                r = spe_DF_clean.rename(columns = {'Sample': 'sampling', 'Sigma': 'SNR', 'Time' : 'time'})
                cur_cluster = SinglePulseEventGroup(cur_list)
#                print(cur_cluster)
                
                if DM_lower_border < cur_min_DM and cur_max_DM < DM_upper_limit:
                    all_clusters.append(cur_cluster)
                else:
                    border_clusters.append(cur_cluster)


#    print(list(lab))
#    print(all_clusters)
#    print(cur_list)
    unique_lab = set(lab)
    unique_lab.discard(-1)
    core_samples_mask = np.zeros_like(lab, dtype=bool)

    d = np.array(df.DM)
    t = np.array(df.time)
    dt = np.stack((d,t), axis=1)

    colors = [plt.cm.Spectral(each) for each in np.linspace(0, 1, len(unique_lab))]
    
    n_border_clusters = len(border_clusters)

#    print("border clusters:", n_border_clusters)

# there are more than one border clusters
    if n_border_clusters > 1:
        for i in range(n_border_clusters - 1):
            cur_cluster = border_clusters[i]
            for j in range((i + 1), n_border_clusters):
                ano_cluster = border_clusters[j]
            # overlapping
                if cur_cluster.max_DM > ano_cluster.min_DM and ano_cluster.min_time < cur_cluster.min_time < ano_cluster.max_time:
                    if cur_cluster.peak_SNR > ano_cluster.peak_SNR:
                        cur_cluster.merge(ano_cluster)
                    else:
                        ano_cluster.merge(cur_cluster)
    # discard merged clusters
        border_clusters = [eachClu for eachClu in border_clusters if eachClu.true_cluster]

    if len(border_clusters) > 0:
        all_clusters.extend(border_clusters)
        
    n_cluster = len(all_clusters)
#    print("number of Clusters: ", n_cluster)
    # first filtering
    if n_cluster < DM_channel_number * obs_length / 100:
        SNR_bound = 5.99
    elif n_cluster < DM_channel_number * obs_length / 100 * 2:
        SNR_bound = 6.49
    elif n_cluster < DM_channel_number * obs_length / 100 * 4:
        SNR_bound = 6.99
    else:
        error_msg = cur_parent_dir + '/' + cur_dir + ',' + 'singlepulses file too large!\n'
        error_log_fp.write(error_msg)
        SNR_bound = 6.99
        # exit("singlepulses file too large!")
#    print("SNR_bound:", SNR_bound)
    
    # define the SNR threshold for dimmer SPEGs, which are checked for recurrences only
    SNR_recur_bound = SNR_bound - 1
    
    # sort the clusters by SNR in descending order
    all_clusters.sort(key=lambda x: x.peak_SNR, reverse=True)
    
    
    """
    merge the clusters (starting from brightest)
    """
#    cur_cluster_DF.rename(columns = {'Sample': 'sampling', 'Sigma': 'SNR', 'Time' : 'time'})
#    print(spe_DF_clean)
    for i in range(n_cluster - 1):
        cur_cluster = all_clusters[i]
    
        if cur_cluster.peak_SNR < SNR_recur_bound:  # merging only starts from bright SPEGs (that have not been merged)
            break
        elif cur_cluster.true_cluster:  # (not been merged)
            # get all single-pulse events
            cur_cluster_DF = spe_DF_clean.loc[(spe_DF_clean['DM'] >= cur_cluster.min_DM) &
                                          (spe_DF_clean['DM'] <= cur_cluster.max_DM) &
                                          (spe_DF_clean['time'] >= cur_cluster.min_time) &
                                          (spe_DF_clean['time'] <= cur_cluster.max_time), ['DM', 'SNR']]
#            print(cur_cluster_DF)
            # sort all single-pulse events by DM
            cur_cluster_DF = cur_cluster_DF.groupby('DM', group_keys=False).apply(lambda x: x.loc[x.SNR.idxmax()])
            # if the SPEG starts and ends with single-pulse events < 5.25, then merging no longer needed
            # this helps to adjust the calculated DM and time range, but may not be necessary
            start_SNR = cur_cluster_DF['SNR'].head(1)
            stop_SNR = cur_cluster_DF['SNR'].tail(1)
            if float(start_SNR) < 5.25 and float(stop_SNR) < 5.25:
                continue
    
            # calculate the DM and time threshold based on expected SNR vs DM curve
            DM_time_thresh = cur_cluster.calc_DM_time_thresh()
    
            for j in range((i + 1), n_cluster):
                ano_cluster = all_clusters[j]
                if ano_cluster.true_cluster:  # not merged yet
                    if DM_time_thresh[0] <= ano_cluster.peak_DM <= DM_time_thresh[1] and \
                            DM_time_thresh[2] <= ano_cluster.peak_time <= DM_time_thresh[3]:
                        cur_cluster.merge(ano_cluster)
    
    """
    update the peak single-pulse event if necessary, after merging, a true cluster is equivalent to an SPEG
    """
    for cur_SPEG in all_clusters:
        if cur_SPEG.true_cluster:
            cur_SPEG_DF = spe_DF_clean.loc[(spe_DF_clean['DM'] >= cur_SPEG.min_DM) &
                                              (spe_DF_clean['DM'] <= cur_SPEG.max_DM) &
                                              (spe_DF_clean['time'] >= cur_SPEG.min_time) &
                                              (spe_DF_clean['time'] <= cur_SPEG.max_time), ]
            peak_row = cur_SPEG_DF.loc[cur_SPEG_DF.SNR.idxmax()]
            # update size
            cur_SPEG.size = len(cur_SPEG_DF.DM)
            cur_SPEG.sizeU = len(cur_SPEG_DF.DM.unique())
            cur_SPEG.peak_DM_spacing = DM_diff_dict.get(cur_SPEG.peak_DM)
            # update peak
            if peak_row['SNR'] > cur_SPEG.peak_SNR:
                cur_SPEG.peak_DM = peak_row[0]
                cur_SPEG.peak_SNR = peak_row[1]
                cur_SPEG.peak_time = peak_row[2]
                cur_SPEG.peak_sampling = peak_row[3]
                cur_SPEG.peak_downfact = peak_row[4]
                cur_SPEG.peak_DM_spacing = DM_diff_dict.get(cur_SPEG.peak_DM)
    
    
    """
    remove duplicates (SPEGs with the same peak single-pulse event)
    """
    a = []
    for i in range(n_cluster - 1):
        cur_SPEG = all_clusters[i]
        if cur_SPEG.true_cluster:
            for j in range((i + 1), n_cluster):
                ano_SPEG = all_clusters[j]
                if ano_SPEG.true_cluster:
                    if cur_SPEG.peak_time == ano_SPEG.peak_time and cur_SPEG.peak_SNR == ano_SPEG.peak_SNR and \
                            cur_SPEG.peak_DM == ano_SPEG.peak_DM:
                        if cur_SPEG.min_DM > ano_SPEG.min_DM and cur_SPEG.max_DM < ano_SPEG.max_DM:
                            cur_SPEG.true_cluster = False
                        else:
                            ano_SPEG.true_cluster = False
                            # print cur_SPEG, ano_SPEG
        a.append(cur_SPEG.peak_SNR)
    # sort the clusters by SNR in descending order
    all_clusters.sort(key=lambda x: x.peak_SNR, reverse=True)
    
    
    all_SPEGs = [cur_SPEG for cur_SPEG in all_clusters if cur_SPEG.true_cluster]
    n_SPEG = len(all_SPEGs)
#    print(all_clusters)

    a = set(a)
    print(len(a))
#    print(len(colors))
#    print(colors.index((0.998077662437524, 0.9992310649750096, 0.7460207612456747, 1.0)))
    for i in range(len(colors)):
        if colors[i] == (0.998077662437524, 0.9992310649750096, 0.7460207612456747, 1.0):
            colors[i] = (0,0,0,1)
#    print(a)
#visualisation of clustering made by DBSCAN on single pulse file
    for w, col, m in zip(unique_lab, colors, a):        
        if len(all_clusters) == 0:
            print(("no cluster"))
            break
        else:
            core_samples_mask[db.core_sample_indices_] = True
            class_members_mask = (lab == w)
            m = (m / max(a))*5
            xy = dt[class_members_mask & core_samples_mask]
#            print(xy)
            plt.plot(xy[:, 1], xy[:, 0], "o", color=tuple(col), linewidth = m, markersize=m)

            xy = dt[class_members_mask & ~core_samples_mask]
#            print(xy)
            plt.plot(xy[:, 1], xy[:, 0], "o", color=tuple(col), linewidth = m, markersize=m)
        plt.xlabel('time')
        plt.ylabel('DM')
        plt.title("max SNR %1.3f" %max(a))
#    plt.show()
#dessin


#    print(cur_SPEG)
    # check SPEGs with lower DM (similar to zeroDM)
    for i in range(n_SPEG - 1):
        cur_SPEG = all_SPEGs[i]
    
        cur_DM_time_extent = cur_SPEG.calc_zero_DM_extent()
    
        # all other SPEGs with in this DM and time extent
        SPEGs_in_extent = [ano_SPEG for ano_SPEG in all_SPEGs
                           if cur_DM_time_extent[0] < ano_SPEG.peak_DM < cur_DM_time_extent[1]
                           and cur_DM_time_extent[2] < ano_SPEG.peak_time < cur_DM_time_extent[3]]
    
        n_SPEGs_in_extent = len(SPEGs_in_extent)
    
        # peak_DM of the brightest (and brighter) SPEG
        brighter_peak_DM = cur_SPEG.peak_DM
        brighter_peak_SNR = cur_SPEG.peak_SNR
    
        n_brighter_SPEGs = 0
        minimum_DM = cur_SPEG.min_DM
    
        # at least one
        if n_SPEGs_in_extent > 0:
            # min DM
            minimum_DM_SPEG = min(SPEGs_in_extent, key=attrgetter('min_DM'))
            if minimum_DM_SPEG.min_DM < minimum_DM:
                minimum_DM = minimum_DM_SPEG.min_DM
    
            brightest_SPEG_in_extent = SPEGs_in_extent[0]
    
            # at least one brighter SPEG
            if brightest_SPEG_in_extent.peak_SNR > cur_SPEG.peak_SNR:
                brighter_peak_DM = brightest_SPEG_in_extent.peak_DM
                brighter_peak_SNR = brightest_SPEG_in_extent.peak_SNR
    
                brighter_SPEGs = [each_SPEG for each_SPEG in SPEGs_in_extent if each_SPEG.peak_SNR > cur_SPEG.peak_SNR]
                n_brighter_SPEGs = len(brighter_SPEGs)
    
        cur_SPEG.n_SPEGs_zero_DM = n_SPEGs_in_extent
        cur_SPEG.n_brighter_SPEGs_zero_DM = n_brighter_SPEGs
        cur_SPEG.SPEGs_zero_DM_min_DM = minimum_DM
        cur_SPEG.brighter_SPEGs_zero_DM_peak_DM = brighter_peak_DM
        cur_SPEG.brighter_SPEGs_zero_DM_peak_SNR = brighter_peak_SNR
    
    SPEG_rank = 1
    bright_SPEGs = []
    dim_SPEGs = []
    
    
    """
    calculate the peak score for each SPEG, assign the cluster rank based on peak SNR, 
    add them to lists of bright and dim SPEGs
    """
    
#    print("...scoring...")
    for cur_SPEG in all_SPEGs:
        # if cur_SPEG.true_cluster:
        if cur_SPEG.peak_DM_spacing < 0.04:
            curMinPts = 8
        else:
            curMinPts = 4
    
        if cur_SPEG.sizeU > curMinPts:  # 5 points in different DM channels at least
            if cur_SPEG.peak_SNR > SNR_recur_bound:
                # find the peak score
                cur_SPEG.find_peak_score()
                # if 8 < cur_SPEG.peak_SNR < 9 and 32.5 < cur_SPEG.peak_time < 33.5 and 212 < cur_SPEG.peak_DM < 222:
                #     print cur_SPEG
    
                # SPEG with peak identified and peak DM > 2
                if cur_SPEG.peak_score > 1 and cur_SPEG.peak_DM > 2:
                    if cur_SPEG.peak_SNR > SNR_bound:
                        cur_SPEG.SPEG_rank = SPEG_rank  # update cluster rank
                        bright_SPEGs.append(cur_SPEG)
                        SPEG_rank += 1  # not only rank the bright pulses
                    else:
                        cur_SPEG.SPEG_rank = SPEG_rank  # update cluster rank
                        dim_SPEGs.append(cur_SPEG)
                        SPEG_rank += 1  # not only rank the bright pulses
    
    
    """
    group SPEGs, find the group rank, group max and median SNR
    """
    
    # curDMrange = [None, None]
    cur_group_rank = 1
    # groupRanks = []
    n_bright_SPEGs = len(bright_SPEGs)
    
    
    # define median function
    def median(lst):
        return np.median(np.array(lst))
    
    
    # grouping
    for i in range(n_bright_SPEGs):
        cur_group = []
        cur_group_SNRs = []
        cur_SPEG = bright_SPEGs[i]
        if not cur_SPEG.grouped:
            # the first element
            cur_group.append(cur_SPEG)
            cur_group_SNRs.append(cur_SPEG.peak_SNR)
            cur_max_SNR = cur_SPEG.peak_SNR
            cur_group_peak_DM = cur_SPEG.peak_DM
            # check other clusters
            for j in range(i + 1, n_bright_SPEGs):
                ano_SPEG = bright_SPEGs[j]
                # not grouped yet
                if not ano_SPEG.grouped:
                    # # contains the peak DM of the group
                    # if ano_SPEG.min_DM <= cur_SPEG.peak_DM <= ano_SPEG.max_DM:
                    # central part overlap
                    if (cur_SPEG.center_stopDM >= ano_SPEG.center_startDM and
                            cur_SPEG.center_startDM <= ano_SPEG.center_stopDM):
                            #and ano_SPEG.min_DM <= cur_group_peak_DM <= ano_SPEG.max_DM):
                        # include into current group
                        cur_group.append(ano_SPEG)
                        cur_group_SNRs.append(ano_SPEG.peak_SNR)
                        ano_SPEG.grouped = True
            # before including dim SPEG
            n_bright_recur_times = len(cur_group)
            # check dim SPEG
            for each_dim in dim_SPEGs:
                # not grouped yet
                if not each_dim.grouped:
                    # central part overlap
                    if (cur_SPEG.center_stopDM >= each_dim.center_startDM and
                            cur_SPEG.center_startDM <= each_dim.center_stopDM and
                            each_dim.min_DM <= cur_group_peak_DM <= each_dim.max_DM):
                        cur_group.append(each_dim)
                        cur_group_SNRs.append(each_dim.peak_SNR)
                        each_dim.grouped = True
            # after including dim SPEG
            n_recur_times = len(cur_group)
            cur_median_SNR = median(cur_group_SNRs)
    
            # assign the group rank and times of recurrences
            for each_SPEG in cur_group:
                each_SPEG.bright_recur_times = n_bright_recur_times
                each_SPEG.recur_times = n_recur_times
                each_SPEG.group_rank = cur_group_rank
                each_SPEG.group_median_SNR = cur_median_SNR
                each_SPEG.group_max_SNR = cur_max_SNR
                each_SPEG.group_peak_DM = cur_group_peak_DM
            # print "cur_group_rank", cur_group_rank
            cur_group_rank += 1
    
#    print("after merging:")
#    print(SPEG_rank - 1)
    
#    print(cur_SPEG)
    """
    open output files to write the SPEGs/clusters, and write header to both files
    """
    header = 'filename' + ',' + 'RA' + ',' + 'Dec' + ',' + 'SPEG_rank' + ',' + 'group_rank' + ','\
             + 'group_peak_DM' + ',' + 'group_max_SNR' + ',' + 'group_median_SNR' + ',' + 'merged' + ','\
             + 'sizeU' + ',' + 'size' + ',' + 'peak_DM_spacing' + ',' + 'peak_DM' + ',' + 'peak_time' + ','\
             + 'peak_SNR' + ',' + 'peak_sampling' + ',' + 'peak_downfact' + ',' \
             + 'min_DM' + ',' + 'max_DM' + ',' + 'min_time' + ',' + 'max_time' + ',' \
             + 'centered_DM' + ',' + 'center_startDM' + ',' + 'center_stopDM' + ',' \
             + 'clipped_SPEG' + ',' + 'SNR_sym_index' + ',' + 'DM_sym_index' + ',' \
             + 'peak_score' + ',' + 'bright_recur_times' + ',' + 'recur_times' + ',' \
             + 'cluster_number' + ',' + 'DM_channel_number' + ',' + 'obs_length' + ','\
             + 'n_SPEGs_zero_DM' + ',' + 'n_brighter_SPEGs_zero_DM' + ','\
             + 'SPEGs_zero_DM_min_DM' + ',' + 'brighter_SPEGs_zero_DM_peak_DM' + ',' + 'brighter_SPEGs_zero_DM_peak_SNR'
    
    out_fp = open('/data/mogier/knee_test/' + '_' + str(q) , 'w')
    out_fp2 = open('/data/mogier/knee_test/' + '_2_' + str(q), 'w')
    
    out_fp.write(header + '\n')
    out_fp2.write(header + '\n')
    
    
    """
    write SPEGs to output files
    """
#    print(bright_SPEGs)
    cur_singlepulses = cur_singlepulses
#    print(cur_singlepulses)
    for cur_SPEG in bright_SPEGs:
        # print cur_SPEG
        result = cur_singlepulses + ',' + cur_RA + ',' + cur_Dec + ',' + str(cur_SPEG.SPEG_rank) + ',' \
                 + str(cur_SPEG.group_rank) + ',' + str(cur_SPEG.group_peak_DM) + ','\
                 + str(cur_SPEG.group_max_SNR) + ',' + str(cur_SPEG.group_median_SNR) + ',' \
                 + str(cur_SPEG.merged) + ',' + str(cur_SPEG.sizeU) + ',' + str(cur_SPEG.size) + ','\
                 + str(cur_SPEG.peak_DM_spacing) + ',' + str(cur_SPEG.peak_DM) + ',' \
                 + str(cur_SPEG.peak_time) + ',' + str(cur_SPEG.peak_SNR) + ',' + str(cur_SPEG.peak_sampling) + ',' \
                 + str(cur_SPEG.peak_downfact) + ',' + str(cur_SPEG.min_DM) + ',' + str(cur_SPEG.max_DM) + ',' \
                 + str(cur_SPEG.min_time) + ',' + str(cur_SPEG.max_time) + ',' \
                 + str(cur_SPEG.centered_DM) + ',' + str(cur_SPEG.center_startDM) + ',' + str(cur_SPEG.center_stopDM) + ','\
                 + str(cur_SPEG.clipped) + ',' + str(cur_SPEG.SNR_sym_index) + ',' + str(cur_SPEG.DM_sym_index) + ',' \
                 + str(cur_SPEG.peak_score) + ',' + str(cur_SPEG.bright_recur_times) + ','\
                 + str(cur_SPEG.recur_times) + ',' + str(n_cluster) + ','\
                 + str(DM_channel_number) + ',' + str(obs_length) + ','\
                 + str(cur_SPEG.n_SPEGs_zero_DM) + ',' + str(cur_SPEG.n_brighter_SPEGs_zero_DM) + ',' \
                 + str(cur_SPEG.SPEGs_zero_DM_min_DM) + ',' + str(cur_SPEG.brighter_SPEGs_zero_DM_peak_DM) + ',' \
                 + str(cur_SPEG.brighter_SPEGs_zero_DM_peak_SNR)
    
    
        out_fp.write(result)
        out_fp.write('\n')  # start a new line
        out_fp2.write(result)
        out_fp2.write('\n')  # start a new line
#    print(dim_SPEGs)
    for cur_SPEG in dim_SPEGs:
        # print cur_SPEG
        result = cur_singlepulses + ',' + cur_RA + ',' + cur_Dec + ',' + str(cur_SPEG.SPEG_rank) + ',' \
                 + str(cur_SPEG.group_rank) + ',' + str(cur_SPEG.group_peak_DM) + ','\
                 + str(cur_SPEG.group_max_SNR) + ',' + str(cur_SPEG.group_median_SNR) + ',' \
                 + str(cur_SPEG.merged) + ',' + str(cur_SPEG.sizeU) + ',' + str(cur_SPEG.size) + ','\
                 + str(cur_SPEG.peak_DM_spacing) + ',' + str(cur_SPEG.peak_DM) + ',' \
                 + str(cur_SPEG.peak_time) + ',' + str(cur_SPEG.peak_SNR) + ',' + str(cur_SPEG.peak_sampling) + ',' \
                 + str(cur_SPEG.peak_downfact) + ',' + str(cur_SPEG.min_DM) + ',' + str(cur_SPEG.max_DM) + ',' \
                 + str(cur_SPEG.min_time) + ',' + str(cur_SPEG.max_time) + ',' \
                 + str(cur_SPEG.centered_DM) + ',' + str(cur_SPEG.center_startDM) + ',' + str(cur_SPEG.center_stopDM) + ',' \
                 + str(cur_SPEG.clipped) + ',' + str(cur_SPEG.SNR_sym_index) + ',' + str(cur_SPEG.DM_sym_index) + ',' \
                 + str(cur_SPEG.peak_score) + ',' + str(cur_SPEG.bright_recur_times) + ',' \
                 + str(cur_SPEG.recur_times) + ',' + str(n_cluster) + ','\
                 + str(DM_channel_number) + ',' + str(obs_length)+ ','\
                 + str(cur_SPEG.n_SPEGs_zero_DM) + ',' + str(cur_SPEG.n_brighter_SPEGs_zero_DM) + ',' \
                 + str(cur_SPEG.SPEGs_zero_DM_min_DM) + ',' + str(cur_SPEG.brighter_SPEGs_zero_DM_peak_DM) + ',' \
                 + str(cur_SPEG.brighter_SPEGs_zero_DM_peak_SNR)
        # print result
        out_fp2.write(result)
        out_fp2.write('\n')  # start a new line
    
    
    """
    close the files
    """
    print('complete')
    out_fp.close()
    out_fp2.close()
    error_log_fp.close()


    return all_clusters
