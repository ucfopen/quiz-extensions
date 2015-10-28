var filter_button = document.getElementById("filter_users_button");
var filter_form = document.getElementById("filter_form");
var filter_text = document.getElementById("filter_users");
var selected_user_list = document.getElementById("selected_user_list");
var user_list = document.getElementById("user_list");

user_list.addEventListener('click', function(e) {
	if (e.target.tagName.toLowerCase() == "li" && e.target.classList.contains("user")) {
		user_li = e.target;
		selected_user_list.appendChild(user_li);
		checkIfEmpty();
	}
});

selected_user_list.addEventListener('click', function(e) {
	if (e.target.tagName.toLowerCase() == "li" && e.target.classList.contains("user")) {
		user_li = e.target;
		user_list.appendChild(user_li);
		checkIfEmpty();
	}
});

filter_button.addEventListener('click', function(e) {
	e.preventDefault();
	var query = filter_text.value;
	ajaxFilter(query, removeAlreadySelected);
});

function ajaxFilter(query, callback) {
	var xhttp = new XMLHttpRequest();

	xhttp.onreadystatechange = function() {
		if (xhttp.readyState == 4 && xhttp.status == 200) {
			user_list.innerHTML = xhttp.responseText;
		}
	}
	xhttp.onload = callback;
	xhttp.open("GET", "/filter/?query=" + query, true);
	xhttp.send();
}

function removeAlreadySelected() {
	// Removes users who are already selected from search results.
	var selected_user_ids = [];
	var users = user_list.children;
	var selected_users = selected_user_list.children;

	for (var i=0; i<selected_users.length; i++) {
		selected_user_ids.push(selected_users[i].getAttribute("data-user-id"));
	}

	for (var i=0; i<users.length; i++) {
		var user_id = users[i].getAttribute("data-user-id");
		if (selected_user_ids.indexOf(user_id) > -1) {
			user_list.removeChild(user_list.children[i]);
		}
	}

	checkIfEmpty();
}

function checkIfEmpty() {
	var user_list_children = user_list.getElementsByClassName("user");

	if (user_list_children.length <= 0) {
		var li = document.createElement("li");
		li.className = "no-matching"
		li.innerHTML = "No matching users found.";
		user_list.appendChild(li);
	}
	else {
		no_matching_warnings = user_list.getElementsByClassName("no-matching");
		for (var i=0; i<no_matching_warnings.length; i++) {
			user_list.removeChild(no_matching_warnings[i]);
		}
	}
}