import click
from pcbnewTransition import pcbnew
import csv
import os
import sys
import shutil
from pathlib import Path
from kikit.fab.common import *
from kikit.common import *
# from kikit.export import gerberImpl
from collections.abc import Iterable




# Based on https://github.com/KiCad/kicad-source-mirror/blob/master/demos/python_scripts_examples/gen_gerber_and_drill_files_board.py
import sys
import os
from pcbnewTransition import pcbnew
from pcbnewTransition.pcbnew import *

from kikit.defs import Layer

fullGerberPlotPlan = [
    # name, id, comment
    ("CuTop", F_Cu, "Top layer"),
    ("CuBottom", B_Cu, "Bottom layer"),
    ("PasteBottom", B_Paste, "Paste Bottom"),
    ("PasteTop", F_Paste, "Paste top"),
    ("SilkTop", F_SilkS, "Silk top"),
    ("SilkBottom", B_SilkS, "Silk top"),
    ("MaskBottom", B_Mask, "Mask bottom"),
    ("MaskTop", F_Mask, "Mask top"),
    ("EdgeCuts", Edge_Cuts, "Edges"),
    ("CmtUser", Cmts_User, "V-CUT")
]

exportSettingsJlcpcb = {
    "UseGerberProtelExtensions": True,
    "UseAuxOrigin": True,
    "ExcludeEdgeLayer": True,
    "MinimalHeader": False,
    "NoSuffix": False,
    "MergeNPTH": False,
    "ZerosFormat": GENDRILL_WRITER_BASE.DECIMAL_FORMAT,
    "SubstractMaskFromSilk": True,
    "UseGerberX2format": True,
    "SubtractMaskFromSilk": True,
}

exportSettingsPcbway = {
    "UseGerberProtelExtensions": True,
    "UseAuxOrigin": False,
    "ExcludeEdgeLayer": True,
    "MinimalHeader": True,
    "NoSuffix": True,
    "MergeNPTH": False,
    "ZerosFormat": GENDRILL_WRITER_BASE.SUPPRESS_LEADING,
}

exportSettingsOSHPark = {
    "UseGerberProtelExtensions": True,
    "UseAuxOrigin": False,
    "ExcludeEdgeLayer": True,
    "MinimalHeader": False,
    "NoSuffix": False,
    "MergeNPTH": True,
    "ZerosFormat": GENDRILL_WRITER_BASE.DECIMAL_FORMAT,
}


def hasCopper(plotPlan):
    for _, layer, _ in plotPlan:
        if layer in [F_Cu, B_Cu]:
            return True
    return False

def setExcludeEdgeLayer(plotOptions, excludeEdge):
    try:
        plotOptions.SetExcludeEdgeLayer(excludeEdge)
    except AttributeError:
        if excludeEdge:
            plotOptions.SetLayerSelection(LSET())
        else:
            plotOptions.SetLayerSelection(LSET(Layer.Edge_Cuts))

def gerberImpl(boardfile, outputdir, plot_plan=fullGerberPlotPlan, drilling=True, settings=exportSettingsJlcpcb):
    """
    Export board to gerbers.

    If no output dir is specified, use '<board file>-gerber'
    """
    board = None
    basename = None
    if isinstance(boardfile, pcbnew.BOARD):
        board = boardfile
        basename = os.path.basename(boardfile.GetFileName())
    else:
        basename = os.path.basename(boardfile)
        board = pcbnew.LoadBoard(boardfile)


    if outputdir:
        plotDir = outputdir
    else:
        plotDir = basename + "-gerber"
    plotDir = os.path.abspath(plotDir)


    pctl = PLOT_CONTROLLER(board)
    popt = pctl.GetPlotOptions()

    popt.SetOutputDirectory(plotDir)

    popt.SetFormat(1)

    popt.SetSketchPadsOnFabLayers(False)
    popt.SetPlotFrameRef(False)
    popt.SetSketchPadLineWidth(FromMM(0.35))
    popt.SetAutoScale(False)
    popt.SetScale(1)
    popt.SetMirror(False)
    popt.SetUseGerberAttributes(False)
    popt.SetIncludeGerberNetlistInfo(True)
    popt.SetCreateGerberJobFile(False)
    popt.SetDisableGerberMacros(False)
    popt.SetUseGerberProtelExtensions(settings["UseGerberProtelExtensions"])
    setExcludeEdgeLayer(popt, settings["ExcludeEdgeLayer"])
    popt.SetScale(1)
    popt.SetUseAuxOrigin(settings["UseAuxOrigin"])
    popt.SetUseGerberX2format(settings["UseGerberX2format"])

    # This by gerbers only
    popt.SetSubtractMaskFromSilk(settings["SubtractMaskFromSilk"])
    popt.SetDrillMarksType(pcbnew.DRILL_MARKS_NO_DRILL_SHAPE)
    popt.SetSkipPlotNPTH_Pads(False)

    # prepare the gerber job file
    jobfile_writer = GERBER_JOBFILE_WRITER(board)

    for name, id, comment in plot_plan:
        if id <= B_Cu:
            popt.SetSkipPlotNPTH_Pads(True)
        else:
            popt.SetSkipPlotNPTH_Pads(False)

        pctl.SetLayer(id)
        suffix = "" if settings["NoSuffix"] else name
        pctl.OpenPlotfile(suffix, PLOT_FORMAT_GERBER, comment)
        jobfile_writer.AddGbrFile(id, os.path.basename(pctl.GetPlotFileName()))
        if pctl.PlotLayer() == False:
            print("plot error")

    if hasCopper(plot_plan):
        #generate internal copper layers, if any
        lyrcnt = board.GetCopperLayerCount()
        for innerlyr in range (1, lyrcnt - 1):
            popt.SetSkipPlotNPTH_Pads(True)
            pctl.SetLayer(innerlyr)
            lyrname = "" if settings["NoSuffix"] else 'inner{}'.format(innerlyr)
            pctl.OpenPlotfile(lyrname, PLOT_FORMAT_GERBER, "inner")
            jobfile_writer.AddGbrFile(innerlyr, os.path.basename(pctl.GetPlotFileName()))
            if pctl.PlotLayer() == False:
                print("plot error")

    # At the end you have to close the last plot, otherwise you don't know when
    # the object will be recycled!
    pctl.ClosePlot()

    if drilling:
        # Fabricators need drill files.
        # sometimes a drill map file is asked (for verification purpose)
        drlwriter = EXCELLON_WRITER(board)
        drlwriter.SetMapFileFormat(PLOT_FORMAT_PDF)

        mirror = False
        minimalHeader = settings["MinimalHeader"]
        if settings["UseAuxOrigin"]:
            offset = board.GetDesignSettings().GetAuxOrigin()
        else:
            offset = VECTOR2I(0, 0)

        # False to generate 2 separate drill files (one for plated holes, one for non plated holes)
        # True to generate only one drill file
        mergeNPTH = settings["MergeNPTH"]
        drlwriter.SetOptions(mirror, minimalHeader, offset, mergeNPTH)
        drlwriter.SetRouteModeForOvalHoles(False)

        metricFmt = True
        zerosFmt = settings["ZerosFormat"]
        drlwriter.SetFormat(metricFmt, zerosFmt)
        genDrl = True
        genMap = True
        drlwriter.CreateDrillandMapFilesSet(pctl.GetPlotDirName(), genDrl, genMap)

        # One can create a text file to report drill statistics
        rptfn = pctl.GetPlotDirName() + 'drill_report.rpt'
        drlwriter.GenDrillReportFile(rptfn)

    job_fn=os.path.dirname(pctl.GetPlotFileName()) + '/' + basename
    job_fn=os.path.splitext(job_fn)[0] + '.gbrjob'
    jobfile_writer.CreateJobFile(job_fn)

def pasteDxfExport(board, plotDir):
    pctl = PLOT_CONTROLLER(board)
    popt = pctl.GetPlotOptions()

    popt.SetOutputDirectory(os.path.abspath(plotDir))
    popt.SetAutoScale(False)
    popt.SetScale(1)
    popt.SetMirror(False)
    setExcludeEdgeLayer(popt, True)
    popt.SetScale(1)
    popt.SetDXFPlotUnits(DXF_UNITS_MILLIMETERS)
    popt.SetDXFPlotPolygonMode(False)

    plot_plan = [
        # name, id, comment
        ("PasteBottom", B_Paste, "Paste Bottom"),
        ("PasteTop", F_Paste, "Paste top"),
        ("EdgeCuts", Edge_Cuts, "Edges"),
    ]

    output = []
    for name, id, comment in plot_plan:
        pctl.SetLayer(id)
        pctl.OpenPlotfile(name, PLOT_FORMAT_DXF, comment)
        output.append(pctl.GetPlotFileName())
        if pctl.PlotLayer() == False:
            print("plot error")
    pctl.ClosePlot()
    return tuple(output)

def dxfImpl(boardfile, outputdir):
    basename = os.path.dirname(boardfile)
    if outputdir:
        plotDir = outputdir
    else:
        plotDir = basename
    plotDir = os.path.abspath(plotDir)

    board = LoadBoard(boardfile)

    pasteDxfExport(board, plotDir)











def collectBom(components, lscsFields, ignore):
    bom = {}
    for c in components:
        if getUnit(c) != 1:
            continue
        reference = getReference(c)
        if "#PWR" in reference or "#FL" in reference:
            continue
        if reference in ignore:
            continue
        if getField(c, "JLCPCB_IGNORE") is not None and getField(c, "JLCPCB_IGNORE") != "":
            continue
        if hasattr(c, "in_bom") and not c.in_bom:
            continue
        if hasattr(c, "on_board") and not c.on_board:
            continue
        if hasattr(c, "dnp") and c.dnp:
            continue
        orderCode = None
        for fieldName in lscsFields:
            orderCode = getField(c, fieldName)
            if orderCode is not None and orderCode.strip() != "":
                break
        cType = (
            getField(c, "Value"),
            getField(c, "Footprint"),
            orderCode
        )
        bom[cType] = bom.get(cType, []) + [reference]
    return bom

def bomToCsv(bomData, filename):
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC"])
        for cType, references in bomData.items():
            # JLCPCB allows at most 200 components per line so we have to split
            # the BOM into multiple lines. Let's make the chunks by 100 just to
            # be sure.
            CHUNK_SIZE = 100
            sortedReferences = sorted(references, key=naturalComponentKey)
            for i in range(0, len(references), CHUNK_SIZE):
                refChunk = sortedReferences[i:i+CHUNK_SIZE]
                value, footprint, lcsc = cType
                writer.writerow([value, ",".join(refChunk), footprint, lcsc])

def exportJlcpcb(board, outputdir, assembly, schematic, ignore, field,
           corrections, correctionpatterns, missingerror, nametemplate, drc,
           autoname, refRenamer: Optional[Callable[[int, str], str]] = None,):
    """
    Prepare fabrication files for JLCPCB including their assembly service
    """
    loadedBoard = None
    if isinstance(board, pcbnew.BOARD):
        loadedBoard = board
    else:
        ensureValidBoard(board)
        loadedBoard = pcbnew.LoadBoard(board)

    if drc:
        ensurePassingDrc(loadedBoard)

    refsToIgnore = parseReferences(ignore)
    removeComponents(loadedBoard, refsToIgnore)
    Path(outputdir).mkdir(parents=True, exist_ok=True)

    gerberdir = os.path.join(outputdir, "gerber")
    shutil.rmtree(gerberdir, ignore_errors=True)
    gerberImpl(board, gerberdir)

    archiveName = expandNameTemplate(nametemplate, "gerbers", loadedBoard)
    shutil.make_archive(os.path.join(outputdir, archiveName), "zip", outputdir, "gerber")

    if not assembly:
        return
    if schematic is None:
        raise RuntimeError("When outputing assembly data, schematic is required")

    correctionFields = [x.strip() for x in corrections.split(",")]

    components = []
    if isinstance(schematic, Iterable) and not isinstance(schematic, str):
        for schem in schematic:
            path = None
            if isinstance(schem, str):
                path = schem
            elif isinstance(schem, dict) and "file" in schem:
                path = schem["file"]

            path = path.strip("\"")
            ensureValidSch(path)
            tmp_components = extractComponents(path)

            if isinstance(schem, dict) and "refRenamer" in schem:
                for component in tmp_components:
                    component.properties["Reference"] = schem["refRenamer"](component.properties["Reference"])
            components += tmp_components
    else:
        # Here we know `schematic` is a single string (not a list/tuple)
        path = schematic.strip("\"")
        ensureValidSch(path)
        components = extractComponents(path)


    ordercodeFields = [x.strip() for x in field.split(",")]
    bom = collectBom(components, ordercodeFields, refsToIgnore)

    bom_refs = set(x for xs in bom.values() for x in xs)
    bom_components = [c for c in components if getReference(c) in bom_refs]

    posData = collectPosData(loadedBoard, correctionFields,
        bom=bom_components, posFilter=noFilter, correctionFile=correctionpatterns)
    boardReferences = set([x[0] for x in posData])
    bom = {key: [v for v in val if v in boardReferences] for key, val in bom.items()}
    bom = {key: val for key, val in bom.items() if len(val) > 0}
    
    missingFields = False
    for type, references in bom.items():
        _, _, lcsc = type
        if not lcsc:
            missingFields = True
            for r in references:
                print(f"WARNING: Component {r} is missing ordercode")
    if missingFields and missingerror:
        sys.exit("There are components with missing ordercode, aborting")


    #ISSUES WHERE FOOTPRINT NAME CONTAINS "JLCPCB" THROWING JLCPCB ONLIEN IMPORTER OFF
    #SO REMOVE LIBRAY PATH, EG "JLCPCB-Footprints:USB-C-SMD_TYPEC-952-ACP24" goes to "USB-C-SMD_TYPEC-952-ACP24"
    def filter_colon(s):
        """If s contains a colon, return the substring after the first colon."""
        return s.split(":", 1)[1] if ":" in s else s
    # If you want to filter the keys (which are tuples) you can do:
    bom = {
        tuple(filter_colon(item) for item in key): value
        for key, value in bom.items()
    }

    posDataToFile(posData, os.path.join(outputdir, expandNameTemplate(nametemplate, "pos", loadedBoard) + ".csv"))
    bomToCsv(bom, os.path.join(outputdir, expandNameTemplate(nametemplate, "bom", loadedBoard) + ".csv"))
