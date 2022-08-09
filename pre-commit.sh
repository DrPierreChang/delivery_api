#!/bin/bash


HEADER_COUNT=4
red=`tput setaf 1`
green=`tput setaf 2`
reset=`tput sgr0`

result=1

languages=('en_US' 'fr_BE' 'fr_CA' 'fr_FR' 'ja' 'ko' 'nl_BE' 'nl_NL' 'es' 'pt_PT')

calculate_count() {
    lines=$(grep $1 <<< "$2")
    count=$(echo "${lines}" | awk 'END {print NR}')
    echo ${count}
}


echo -e "\n\n${green}Validation before commit started${reset}"

for language in "${languages[@]}"
do
django-admin makemessages -l ${language}
messages_changes=$(git diff --color=never --unified=0 ./conf/locale/${language}/LC_MESSAGES/)

if [[ "$messages_changes" == "" ]]; then
    echo "${green}File 'django.po' has not any changes.${reset}"
	result=0
else
    total_lines=$(echo "${messages_changes}" | awk 'END {print NR}')

    info_lines=$(calculate_count '^@@' "$messages_changes")

    changed_lines=$(calculate_count '^[-+]#.*$' "$messages_changes")

    correct_lines=$(( $changed_lines + $info_lines + $HEADER_COUNT ))

    if [[ $correct_lines == $total_lines ]]; then
        echo "${green}File 'django.po' automatically updated and added to last commit.${reset}"
        git add ./conf/locale/en_US/LC_MESSAGES/
        result=0
    else
        echo "-----------------------"
        echo "${red}You have unstaged changes in 'django.po'"
        echo "Please add translations for new strings and add 'django.po' to commit${reset}"

        git diff --color=always --stat ./conf/locale/${language}/LC_MESSAGES/
        result=1
    fi
fi

if [[ $result == 0 ]]; then
    echo -e "${green}Validation before commit done${reset}\n\n"
fi
done

exit ${result}