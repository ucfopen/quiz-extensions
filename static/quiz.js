var filter_button = document.getElementById("filter_users_button");
var filter_text = document.getElementById("filter_users");
var selected_user_list = document.getElementById("selected_user_list");
var user_list = document.getElementById("user_list");
var user_list_div = document.getElementById("user_list_div");
var percent_added_span = document.getElementById("modal_percent_added");
var missing_alert = document.getElementById('missing_alert');
var modal_selected_user_list = document.getElementById("modal_selected_user_list");
var percent_form = document.getElementById("percent_form");
var percent_select = document.getElementById("percent_select");
var percent_input = document.getElementById("percent_input");
var go_button = document.getElementById("go_button");
var clear_button = document.getElementById("clear_button");
var submit_button = document.getElementById("submit_button");
var update_status = document.getElementById("update_status");
var close_button = document.getElementById("close_button");
var close_x = document.getElementById("close_x");
var i = 0;

user_list_div.addEventListener('click', function(e) {
	e.preventDefault();

	if (e.target.tagName.toLowerCase() == "button" && e.target.classList.contains("user")) {
		var user_button = e.target;

		var user_id = user_button.getAttribute("data-user-id");

		var is_duplicate = false;
		for (i=0; i<selected_user_list.children.length; i++) {
			var selected_user = selected_user_list.children[i];
			if (selected_user.getAttribute("data-user-id") == user_id) {
				is_duplicate = true;
				break;
			}
		}
		if (!is_duplicate) {
			var new_user_button = user_button.cloneNode(true);
			selected_user_list.appendChild(new_user_button);
		}

		user_button.disabled = true;
		checkIfEmpty();
	}
	else if (e.target.id == "prev_user_page_button" || e.target.id == "next_user_page_button") {
		var query = filter_text.value;
		var page_number = e.target.getAttribute("data-page-number");

		ajaxFilter(query, page_number, update_user_list);
	}
});

selected_user_list.addEventListener('click', function(e) {
	if (e.target.tagName.toLowerCase() == "button" && e.target.classList.contains("user")) {
		var selected_user_li = e.target;
		var selected_user_id = selected_user_li.getAttribute("data-user-id");

		for (i=0; i<user_list.children.length; i++) {
			var user = user_list.children[i];
			if (user.getAttribute("data-user-id") == selected_user_id) {
				user.disabled = false;
			}
		}

		selected_user_list.removeChild(selected_user_li);

		checkIfEmpty();
	}
});

filter_button.addEventListener('click', function(e) {
	e.preventDefault();
	var query = filter_text.value;
	ajaxFilter(query, curr_page_number, update_user_list);
});

percent_select.addEventListener('change', function(e) {
	percent_added_span.innerHTML = getPercent();
});

percent_input.addEventListener('input', function(e) {
	percent_added_span.innerHTML = getPercent();
});

go_button.addEventListener('click', function(e) {
	percent_added_span.innerHTML = getPercent();

	modal_selected_user_list.innerHTML = "";
	var num_selected_users = selected_user_list.children.length;

	if (num_selected_users === 0) {
		submit_button.disabled = true;
	}
	else {
		submit_button.style.display = "";
		submit_button.disabled = false;
	}

	for (i=0; i<num_selected_users; i++) {
		var user_id = selected_user_list.children[i].getAttribute("data-user-id");
		var user_name = selected_user_list.children[i].innerHTML;

		var new_li = document.createElement("LI");
		new_li.setAttribute("data-user-id", user_id);
		new_li.innerHTML = user_name;

		modal_selected_user_list.appendChild(new_li);
	}
});

clear_button.addEventListener('click', function(e) {
	clearSelectedStudents();
});

submit_button.addEventListener('click', function(e) {
	ajaxSend();
});

function checkStatus(id) {
	// TODO: Write this
	console.log('hello world!');
}

document.getElementById('refresh_link').addEventListener('click', function(e) {
	e.preventDefault();

	var refresh_url = e.target.getAttribute('href');

	$.post(refresh_url)
		.done(function(data) {
			console.log(data);
			var interval_id = setInterval(checkStatus, 1000, data);
		})
		.fail(function(data) {
			// TODO: handle error case
		});

	// var xhttp = new XMLHttpRequest();

	// xhttp.onreadystatechange = function() {
	// 	if (xhttp.readyState == 4) {
	// 		debugger;
	// 		var alerts_div = document.getElementById('alerts');

	// 		var test_url = xhttp.responseText;

	// 		var alert = document.createElement('div');
	// 		var close_alert_text = '<a href="#" class="close" data-dismiss="alert" aria-label="close">&times;</a>'
	// 		alert.innerHTML = close_alert_text + "<p>" + response['message'] + "</p>";

	// 		if (xhttp.status == 200 && response['success'] == true) {
	// 			missing_alert.style.display = "none";
	// 			alert.className = 'alert alert-success fade in';
	// 		}
	// 		else {
	// 			missing_alert.style.display = "";
	// 			alert.className = 'alert alert-danger fade in';
	// 		}

	// 		alerts_div.appendChild(alert);
	// 	}
	// };
	// xhttp.open("POST", refresh_url, true);
	// xhttp.send();
});

$("#go_modal").on('hidden.bs.modal', function(e) {
	percent_form.style.display = "";
	update_status.style.display = "none";
});

function clearSelectedStudents() {
	var num_selected_users = selected_user_list.children.length;

	while (selected_user_list.children.length > 0) {
		selected_user_list.children[0].click();
	}
}

function clearAlerts() {
	var alerts_div = document.getElementById('alerts');
	while(alerts_div.children.length > 0) {
		alerts_div.removeChild(alerts_div.children[0]);
	}
}

function ajaxFilter(query, page, callback) {
	var xhttp = new XMLHttpRequest();

	user_list_div.innerHTML = "<div id=\"user_list\"><p>loading...</p></div>";

	xhttp.onreadystatechange = function() {
		if (xhttp.readyState == 4 && xhttp.status == 200) {
			user_list_div.innerHTML = xhttp.responseText;
		}
	};
	xhttp.onload = callback;
	xhttp.open("GET", filter_url+"?query=" + query + "&page=" + page, true);
	xhttp.send();
}

function getPercent() {
	if (percent_input.value !== null && percent_input.value !== "") {
		percent_select.disabled = true;
		if (percent_input.value >= 100) {
			return percent_input.value;
		}
		else {
			return percent_select.value;
		}
	}
	else {
		percent_select.disabled = false;
		return percent_select.value;
	}
}

function ajaxSend() {
	var xhttp = new XMLHttpRequest();

	var selected_users = selected_user_list.children;

	var users_percent_obj = {
		user_ids: [],
		percent: getPercent()
	};

	for (i=0; i<selected_users.length; i++) {
		var user_id = selected_users[i].getAttribute("data-user-id");
		users_percent_obj.user_ids.push(user_id);
	}

	xhttp.onreadystatechange = function() {
		if (xhttp.readyState == 1) {
			submit_button.style.display = "none";
			close_button.disabled = true;
			close_x.style.display = "none";

			update_status.innerHTML = "<p>Processing...</p><p>(This may take a few minutes)</p>";

			percent_form.style.display = "none";
			update_status.style.display = "";
			return;
		}

		if (xhttp.readyState == 4) {
			if (xhttp.status == 200) {
				var response = JSON.parse(xhttp.responseText);
				update_status.innerHTML = "<p>"+ response["message"] + "</p>";
				if (!response["error"]) {
					var quiz_list = response["quiz_list"];
					if (quiz_list.length > 0) {
						update_status.innerHTML += "<h4>Updated</h4>"
						var table_html = "<div id='table_div'><table class='table table-striped table-condensed'><thead><tr><th scope='col'>Quiz Title</th><th scope='col'>Minutes Extended</th></tr></thead><tbody>";
						for (var x in quiz_list) {
							table_html += "<tr><td>" +
								quiz_list[x]["title"] +
								"</td><td>" +
								quiz_list[x]["added_time"] +
								"</td></tr>";
						}
						table_html += "</tbody></table></div>";
						update_status.innerHTML += table_html;
					}
					else {
						update_status.innerHTML += "<p>No Quizzes were found.</p>"
					}

					var unchanged_quiz_list = response["unchanged_list"];
					if (unchanged_quiz_list.length > 0) {
						update_status.innerHTML += "<h4>Unchanged</h4>"
						var unchanged_table_html = "<div id='table_div'><table class='table table-striped table-condensed'><thead><tr><th scope='col'>Quiz Title</th></tr></thead><tbody>";
						for (var x in unchanged_quiz_list) {
							unchanged_table_html += "<tr><td>" +
								unchanged_quiz_list[x]["title"] +
								"</td></tr>";
						}
						unchanged_table_html += "</tbody></table></div>";
						update_status.innerHTML += unchanged_table_html;
					}
				}
				clearSelectedStudents();
				clearAlerts();
				percent_input.value = "";
			}
			else {
				update_status.innerHTML = "<p>Encountered an error. Status "+ xhttp.status + "</p>";
			}
			close_button.disabled = false;
			close_x.style.display = "";
			return;
		}
	};

	xhttp.open("POST", update_url, true);
	xhttp.setRequestHeader("Content-Type", "application/json");
	xhttp.send(JSON.stringify(users_percent_obj));
}

function update_user_list() {
	user_list = document.getElementById("user_list");
	selected_user_list = document.getElementById("selected_user_list");
	disableAlreadySelected();
	checkIfEmpty();
}

function disableAlreadySelected() {
	// grays out users who are already selected from search results.
	var selected_user_ids = [];
	var users = user_list.children;
	var selected_users = selected_user_list.children;

	for (i=0; i<selected_users.length; i++) {
		selected_user_ids.push(selected_users[i].getAttribute("data-user-id"));
	}

	for (i=0; i<users.length; i++) {
		var user_id = users[i].getAttribute("data-user-id");
		if (selected_user_ids.indexOf(user_id) > -1) {
			user_list.children[i].setAttribute("disabled", true);
		}
	}
}

function checkIfEmpty() {
	var user_list_children = user_list.getElementsByClassName("user");

	if (user_list_children.length <= 0) {
		var p = document.createElement("p");
		p.className = "no-matching";
		p.innerHTML = "No matching students found.";
		user_list.appendChild(p);
	}
	else {
		no_matching_warnings = user_list.getElementsByClassName("no-matching");
		for (i=0; i<no_matching_warnings.length; i++) {
			user_list.removeChild(no_matching_warnings[i]);
		}
	}
}

function ajax_check_missing_quizzes(course_id) {
	var xhttp = new XMLHttpRequest();

	xhttp.onreadystatechange = function() {
		if (xhttp.readyState == 4 && xhttp.status == 200) {
			var response = JSON.parse(xhttp.responseText);

			if (response) {
				missing_alert.style.display = "";
			}
			else {
				missing_alert.style.display = "none";
			}
		}
	};
	xhttp.open("GET", missing_quizzes_url, true);
	xhttp.send();
}

function load_func() {
	// load initial user list
	ajaxFilter('', 1, update_user_list);

	// check for missing quizzes
	ajax_check_missing_quizzes(course_id);
}

window.onload = load_func;
