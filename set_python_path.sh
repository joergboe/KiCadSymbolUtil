# This script must be sourced!
echo $0
if [[ 'set_python_path.sh' != $(basename $0) ]]; then
	if [[ -z "$PYTHONPATH" ]]; then
		export	PYTHONPATH=~/git/kicad-library-utils/common
	else
		echo "PYTHONPATH is already set"
		echo "PYTHONPATH=$PYTHONPATH"
	fi
else
	echo "This script must be sourced!"
	echo
	echo "Usage: source $0"
fi
