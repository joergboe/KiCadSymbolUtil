# This script must be sourced!

if [[ 'set_python_path.sh' != $(basename $0) ]]; then
	export	PYTHONPATH="${PYTHONPATH}:${PWD}/../kicad-library-utils/common"
	echo "PYTHONPATH changed!"
	echo "PYTHONPATH=${PYTHONPATH}"
else
	echo "This script must be sourced!" >&2
	echo >&2
	echo "Usage: source $0" >&2
	exit 1
fi
