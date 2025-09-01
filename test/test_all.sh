#!/usr/bin/env bash

declare -A RESULTS=(
[000-Empty.csv]=3
[001-CSVError.csv]=3
[010-Header1Missing.csv]=3
[011-Header1Surplus.csv]=3
[012-Header1Surplus1.csv]=3
[013-Header1Double.csv]=3
[014-Header1Wrong.csv]=3
[015-Header1Only.csv]=3
[020-Header2Missing.csv]=3
[021-Header2Surplus.csv]=3
[022-Header2Surplus2.csv]=3
[023-Header2Double.csv]=3
[024-Header2Wrong.csv]=3
[025-Header12Only.csv]=0
[030-MinSymbol.csv]=0
[031-MinSymbolMissing.csv]=3
[032-MinSymbolSurplus1.csv]=3
[033-MinSymbolEmptyLines.csv]=0
[040-MaxSymbol.csv]=0
[041-MaxSymbolWrong.csv]=3
[050-MinPin.csv]=0
[051-MinPinTextGaps.csv]=0
[052-MinPinDuplicateNumber.csv]=3
[053-MinPinAlternatStacked.csv]=3
[061-MaxPinWrong.csv]=3
[062-MaxPinWrogLenPaddingCombi.csv]=3
[063-MaxPinAltFuncHidden.csv]=3
[068-MaxPinWrongAltSide.csv]=3
[069-MaxPinBusWrongAltSet.csv]=3
[070-MaxPinPinCounts.csv]=0
[071-MaxPinGapWrong.csv]=3
[072-MaxPinGaps.csv]=0
[073-MaxPinBusHiddenStackedGap.csv]=0
[074-MaxPinBus1.csv]=0
[075-MaxPinBusReverse.csv]=0
[076-MaxPinBusGapPinAlternative.csv]=0
[077-MaxPinBusAlternative.csv]=0
[078-MaxPinBusAlternative2.csv]=0
[079-MaxPinBusAlternativeStackedHidden.csv]=0
[080-SymbolDouble.csv]=3
[081-SymbolExtendsFailures.csv]=3
[085-BaseSymbolWrongCat.csv]=3
[086-DerivedSymbolNoBase.csv]=3
[090-DerivedSymbolPinDel.csv]=0
[091-DerivedSymbolPinDelAltFunc.csv]=0
[092-DerivedSymbolPinDelBus.csv]=0
[093-DerivedSymbolPinDelNotFound.csv]=3
[094-DerivedSymbolPinInsBefore.csv]=0
[095-DerivedSymbolPinInsBeforeAlt.csv]=0
[096a-DerivedSymbolNotFound.csv]=3
[096-DerivedSymbolPinInsBeforeNotFound.csv]=3
[097-DerivedSymbolPinInsAfterNotFound.csv]=3
[098-DerivedSymbolPinInsAfter.csv]=0
[099-DerivedSymbolPinInsAfterAltFunc.csv]=0
[100-DerivedSymbolPinDelInsIns.csv]=0
[101-DerivedSymbolPinOverloadNotFound.csv]=3
[105-DerivedSymbolDelNoNum.csv]=3
[106-DerivedSymbolOverloadWithNumber.csv]=3
[107-DerivedSymbolOverloadPin.csv]=0
[108-DerivedSymbolOverloadPinAlternative.csv]=0
[109-DerivedSymbolOverloadBusAlternative.csv]=0
[110-DerivedSymbolPinOverloadAfterIns.csv]=0
[111-DerivedSymbolExNameAndPos.csv]=0
[112-DerivedSymbolExNameAndPosBus.csv]=0
)

SUMFILE='results.sum'

declare -i test_count=0
declare -i failure_count=0
declare -i unknown_cases=0

DATE="$(date)"

{
	echo "*******************************************"
	echo "Testrun: ${DATE}"
	echo "*******************************************"
} >> "${SUMFILE}"


for case in *.csv; do
	echo "Test ${case}"
	rm a.kicad_sym
	if [[ -n "${RESULTS[${case}]}" ]]; then
		for debug in -vv -v '' -s; do
			test_count+=1
			../csv_to_kicad.py ${debug} "${case}"
			RES=$?
			if [[ "${RESULTS[${case}]}" == "${RES}" ]]; then
				echo "SUCCESS: ../csv_to_kicad.py ${debug} ${case}" >> "${SUMFILE}"
			else
				echo "ERROR: ../csv_to_kicad.py ${debug} ${case} failed: Return Code = ${RES}" >> "${SUMFILE}"
				failure_count+=1
			fi
		done
	else
		echo "ERROR: case ${case} is not in result list RESULTS" >> "${SUMFILE}"
		unknown_cases+=1
	fi
done

echo "Number of cases = ${test_count}"
echo "Number failed cases = ${failure_count}"
echo "Number of unknown cases = ${unknown_cases}"

{
	echo "Number of cases = ${test_count}"
	echo "Number failed cases = ${failure_count}"
	echo "Number of unknown cases = ${unknown_cases}"
} >> "${SUMFILE}"

if [[ ${failure_count} = 0 && ${unknown_cases} = 0 ]];	then
	echo "*****************"
	echo " SUCCESS"
	echo "*****************"
	exit 0
else
	echo "*****************" >&2
	echo " ERRORS" >&2
	echo "*****************" >&2
	exit 1
fi
