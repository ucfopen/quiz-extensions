var filter_button = document.getElementById("filter_users_button");
var filter_form = document.getElementById("filter_form");
var filter_text = document.getElementById("filter_users");
var selected_user_list = document.getElementById("selected_user_list");
var user_list = document.getElementById("user_list");
var percent_added_span = document.getElementById("modal_percent_added");
var modal_selected_user_list = document.getElementById("modal_selected_user_list");
var percent_select = document.getElementById("percent_select");
var percent_input = document.getElementById("percent_input");
var confirm_button = document.getElementById("confirm_button");
var submit_button = document.getElementById("submit_button");

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

percent_select.addEventListener('change', function(e) {
	percent_added_span.innerHTML = getPercent();
});

percent_input.addEventListener('keyup', function(e) {
	percent_added_span.innerHTML = getPercent();
});

confirm_button.addEventListener('click', function(e) {
	percent_added_span.innerHTML = getPercent();

	modal_selected_user_list.innerHTML = "";
	for (var i=0; i<selected_user_list.children.length; i++) {
		modal_selected_user_list.appendChild(selected_user_list.children[i].cloneNode(true));
	}

});

submit_button.addEventListener('click', function(e) {
	// for (var i=0; i<modal_selected_user_list.children.length; i++) {
	// 	modal_selected_user_list.children[i].getAttribute("data-user-id")
	// }
	ajaxSend(function(){
		console.log("done!");
	})
})

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

function getPercent() {
	if (percent_input.value != null && percent_input.value >= 100) {
		return percent_input.value;
	}
	else {
		return percent_select.value.replace(/%/g, '');
	}
}

function ajaxSend(query, callback) {
	var xhttp = new XMLHttpRequest();

	var selected_users = selected_user_list.children;

	var users_percent_obj = {
		user_ids: [],
		percent: getPercent()
	};

	for (var i=0; i<selected_users.length; i++) {
		var user_id = selected_users[i].getAttribute("data-user-id");
		users_percent_obj.user_ids.push(user_id);
	}

	xhttp.onreadystatechange = function() {
		if (xhttp.readyState == 4 && xhttp.status == 200) {
			// Server responded with 200. Check xhttp.responseText. Do things.
		}
	}
	console.log(JSON.stringify(users_percent_obj));
	xhttp.onload = callback;
	xhttp.open("POST", "/update/", true);
	xhttp.setRequestHeader("Content-Type", "application/json");
	xhttp.send(JSON.stringify(users_percent_obj));
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