'''
Blue Raster Technical Interview Script
04/2022
J. Beasley 

Requirements:
    - Use ArcPy
    - Output CSV count of fires grouped by country
    - Within same CSV, output highest confidence
        fire in each country with a fire. 
    - Fire: https://firms.modaps.eosdis.nasa.gov/data/active_fire/modisc6.1/csv/MODIS_C6_1_South_America_7d.csv
Optional: 
    - For each fire, find average distance to all other fires
    - Find fires that are within 5 km of a border
'''

import arcpy
import csv
from datetime import datetime
import logging
import os
import sys

arcpy.env.overwriteOutput = True

def writeCSV(out_csv, csv_cols, in_tab, scur_flds):

    with open(out_csv, 'w', newline='') as fcsv:
        wcsv = csv.writer(fcsv)
        wcsv.writerow(csv_cols)
        with arcpy.da.SearchCursor(in_tab, scur_flds) as scur:
            for row in scur:
                vals = [r for r in row]
                wcsv.writerow(vals)
    fcsv.close()


def getFiresByCountry(in_csv, x, y, conf_lvl, in_bnd, bnd_id, out_path, findAvgDist = True, findNearBorder = True):

    today = datetime.now().strftime('%m%d%Y')

    # ensure data are in same sr
    sr = arcpy.Describe(in_bnd).spatialReference

    logging.info('Converting rows to points...')
    xy_fc = arcpy.XYTableToPoint_management(in_csv, r'in_memory\xy_fc', x, y)
    fires_pnt = arcpy.Project_management(xy_fc, arcpy.env.scratchGDB + r'\fire_pnt', sr)

    # check data alignment
    data_check = arcpy.SelectLayerByLocation_management(fires_pnt, 'WITHIN', in_bnd, '', 'NEW_SELECTION', 'INVERT')
    check_cnt = int(arcpy.GetCount_management(data_check)[0])
    if check_cnt > 0:
        logging.warning(f'{str(check_cnt)} point(s) fall outside of boundaries!')
        logging.warning('These data will not be included when summing by intersection!')

    logging.info('Finding boundary shapes containing points...')
    bnd_w_fire = arcpy.SelectLayerByLocation_management(in_bnd, 'CONTAINS', fires_pnt, selection_type='NEW_SELECTION')

    logging.info('Finding point count and maximum confidence level by boundary...')
    # keep_all_polygons param less efficient, used select by loc
    sum_within = arcpy.SummarizeWithin_analysis(bnd_w_fire, fires_pnt, r'in_memory\fire_by_bnd', sum_fields=[[conf_lvl, 'MAX']])

    logging.info(f'Summarizing by {bnd_id}')
    stat_tab = arcpy.Statistics_analysis(sum_within, r'in_memory\stat_tab', statistics_fields=[['Point_Count', 'SUM'], [f'max_{conf_lvl}', 'MAX']], case_field=bnd_id)

    logging.info('Clean up...')
    rename = {bnd_id:bnd_id.title(), 'SUM_Point_Count':'Count', f'MAX_max_{conf_lvl}':f'Max {conf_lvl.title()}'}

    logging.info('Creating output CSV...')
    writeCSV(out_path + f'\MODIS_fires_countByCountry_{today}.csv', list(rename.values()), stat_tab, list(rename.keys()))

    if findAvgDist:

        logging.info('Finding average distance to all fires...')

        def getAvgDistToFires(pnts):

            logging.info('Finding distances to all fires...')
            near = arcpy.GenerateNearTable_analysis(pnts, pnts, r'in_memory\near_tab', closest = 'ALL', method='PLANAR')

            logging.info('Averaging distances...')
            avg_dist = arcpy.Statistics_analysis(near, arcpy.env.scratchGDB + r'\avg_dist', [['NEAR_DIST', 'MEAN']], 'IN_FID')

            logging.info('Joining avergae distance...')
            arcpy.JoinField_management(pnts, 'OBJECTID', avg_dist, 'IN_FID', ['MEAN_NEAR_DIST'])

            logging.info('Creating output CSV...')
            all_flds = [f.name for f in arcpy.ListFields(pnts) if not f.required]
            final_flds = ['Average Dist. to All Other Fires (meters)' if x == 'MEAN_NEAR_DIST' else x for x in all_flds]

            writeCSV(out_path + f'\MODIS_fires_avgDistToAllFires_{today}.csv', final_flds, pnts, all_flds)

            logging.info('Clean up...')
            arcpy.DeleteField_management(pnts, 'MEAN_NEAR_DIST')


        getAvgDistToFires(fires_pnt)

    if findNearBorder:

        logging.info('Finding fires within a distance to a border...')
    
        def getFiresWithinDistToBorder(pnts, bnds, dist=5, unit='KILOMETERS'):

            logging.info('Converting boundaries to lines...')
            bnd_lines = arcpy.PolygonToLine_management(bnds, r'in_memory\bnd_lines')

            logging.info(f'Finding points within {str(dist)} {unit.lower()} to a border...')
            select_fires = arcpy.SelectLayerByLocation_management(pnts, 'WITHIN_A_DISTANCE', bnd_lines, f'{str(dist)} {unit}', 'NEW_SELECTION')

            logging.info('Creating output CSV...')
            all_flds = [f.name for f in arcpy.ListFields(pnts) if not f.required]

            writeCSV(out_path + f'\MODIS_fires_{str(dist)}{unit.title()}ToBorders_{today}.csv', all_flds, select_fires, all_flds)

        
        getFiresWithinDistToBorder(fires_pnt, bnd_w_fire)


if __name__ == '__main__':

    working_fldr = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    today = datetime.now().strftime('%m%d%Y')

    logfile = working_fldr + r"\logs\technicalInterview_{0}.log".format(today)
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)s: %(asctime)s %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S', 
                        handlers=[logging.FileHandler(logfile),
                                logging.StreamHandler(sys.stdout)])

    # inputs
    fire_csv = working_fldr + r'\supp-data\MODIS_C6_1_South_America_7d.csv'
    x_fld = 'longitude'
    y_fld = 'latitude'
    confidence_fld = 'confidence'

    country_bnd = 'https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/World_Countries/FeatureServer/0'
    country_id = 'COUNTRY'

    # outputs
    out_csv_path = working_fldr + f'\outputs'

    logging.info('Starting run...')

    try:
        logging.info(f'Finding point count by {country_id}')
        getFiresByCountry(fire_csv, x_fld, y_fld, confidence_fld, country_bnd, country_id, out_csv_path, True, True)

    except PermissionError as e:
        logging.error("PERMISSION ERROR")
        logging.error(e)
        logging.error('Ensure all previously created CSVs are closed!')
        logging.error('Check that supporting data is not open in another program (ArcGIS Pro/Map/Catalog)!')

    except Exception as e:
        logging.error("EXCEPTION OCCURRED")
        logging.error(e)

    logging.info('Finished run')
    logging.info('---------------------------------------------------------\n')
